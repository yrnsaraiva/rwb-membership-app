"""Painel de gestão do clube (RF-06): membros, eventos, presenças, moderação e relatórios básicos."""
import csv
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.activity import services as activity
from apps.activity.models import PointTransaction, Run
from apps.billing.models import Subscription
from apps.events import services as event_services
from apps.events import ticket_checkin
from apps.events.models import Event, Registration
from apps.shop import services as shop_services
from apps.shop.models import Order

from .forms import ActivateSubscriptionForm, EventForm, ExternalEventForm, PointsAdjustForm

User = get_user_model()
staff_required = staff_member_required(login_url="accounts:login")


@staff_required
def index(request):
    now = timezone.now()
    today = timezone.localdate()
    month_start = today.replace(day=1)
    last_30 = today - timedelta(days=30)
    members = User.objects.filter(is_active=True)
    runs_month = Run.objects.valid().filter(date__gte=month_start)
    upcoming = Event.objects.upcoming().with_counts()[:6]
    top = (
        members.annotate(km=Sum("runs__distance_km", filter=Q(runs__is_valid=True, runs__date__gte=month_start)))
        .filter(km__gt=0).order_by("-km")[:5]
    )
    context = {
        "kpi": {
            "members": members.count(),
            "new_members": members.filter(date_joined__date__gte=month_start).count(),
            "active_members": members.filter(runs__date__gte=last_30, runs__is_valid=True).distinct().count(),
            "premium": Subscription.objects.active().values("user").distinct().count(),
            "km_month": runs_month.aggregate(k=Sum("distance_km"))["k"] or 0,
            "runs_month": runs_month.count(),
            "registrations_30d": Registration.objects.filter(
                created_at__gte=now - timedelta(days=30), status=Registration.Status.CONFIRMED
            ).count(),
            "pending_subs": Subscription.objects.pending().count(),
            "pending_orders": Order.objects.filter(status=Order.Status.PENDING).count(),
            "orders_to_deliver": Order.objects.filter(status__in=[Order.Status.PAID, Order.Status.READY]).count(),
            "shop_revenue_month": Order.objects.filter(paid_at__date__gte=month_start).aggregate(t=Sum("total_mzn"))["t"] or 0,
        },
        "upcoming": upcoming,
        "top": top,
        "signups": _signups_by_week(),
    }
    return render(request, "panel/index.html", context)


def _signups_by_week(weeks=8):
    today = timezone.localdate()
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    dates = User.objects.filter(date_joined__date__gte=start).values_list("date_joined", flat=True)
    counts = [0] * weeks
    for dt in dates:
        idx = (timezone.localtime(dt).date() - start).days // 7
        if 0 <= idx < weeks:
            counts[idx] += 1
    peak = max(counts) or 1
    return [{"label": f"{start + timedelta(weeks=i):%d/%m}", "count": c, "height": round(c / peak * 100)}
            for i, c in enumerate(counts)]


# --- Membros -------------------------------------------------------------------------
@staff_required
def members(request):
    q = request.GET.get("q", "").strip()
    qs = User.objects.all().order_by("-date_joined")
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
                       | Q(member_number__icontains=q) | Q(phone__icontains=q))
    if request.GET.get("formato") == "csv":
        return _members_csv(qs)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "panel/members.html", {"page": page, "q": q})


def _members_csv(qs):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="membros-rwb.csv"'
    response.write("﻿")  # BOM para o Excel abrir acentos correctamente
    writer = csv.writer(response)
    writer.writerow(["Nº sócio", "Nome", "Apelido", "Email", "Telemóvel", "Cidade", "Activo", "Registo"])
    for u in qs:
        writer.writerow([u.member_number, u.first_name, u.last_name, u.email, u.phone, u.city,
                         "sim" if u.is_active else "não", timezone.localtime(u.date_joined).strftime("%Y-%m-%d")])
    return response


@staff_required
@require_http_methods(["GET", "POST"])
def member_detail(request, pk):
    member = get_object_or_404(User, pk=pk)
    form = PointsAdjustForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        PointTransaction.objects.create(
            user=member, amount=form.cleaned_data["amount"], reason=PointTransaction.Reason.ADJUSTMENT,
            description=form.cleaned_data["description"],
        )
        messages.success(request, "Ajuste de pontos registado.")
        return redirect("panel:member_detail", pk=member.pk)
    return render(request, "panel/member_detail.html", {
        "member": member,
        "stats": activity.member_stats(member),
        "runs": member.runs.all()[:10],
        "registrations": member.registrations.select_related("event").order_by("-event__starts_at")[:10],
        "subscriptions": member.subscriptions.select_related("plan")[:10],
        "points": member.point_transactions.all()[:10],
        "form": form,
    })


@staff_required
@require_POST
def member_toggle_active(request, pk):
    member = get_object_or_404(User, pk=pk)
    if member == request.user:
        messages.error(request, "Não podes desactivar a tua própria conta.")
    else:
        member.is_active = not member.is_active
        member.save(update_fields=["is_active"])
        messages.success(request, f"Conta {'reactivada' if member.is_active else 'desactivada'}.")
    return redirect("panel:member_detail", pk=member.pk)


# --- Eventos -------------------------------------------------------------------------
@staff_required
def events(request):
    tab = request.GET.get("tab", "proximos")
    qs = Event.objects.with_counts()
    now = timezone.now()
    qs = qs.filter(starts_at__lt=now).order_by("-starts_at") if tab == "passados" else qs.filter(starts_at__gte=now).order_by("starts_at")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "panel/events.html", {"page": page, "tab": tab})


@staff_required
@require_http_methods(["GET", "POST"])
def event_form(request, pk=None):
    event = get_object_or_404(Event, pk=pk) if pk else None
    if event is None and settings.ETK_ENABLED:
        messages.info(request, "Os eventos são criados na ETK e sincronizados para aqui.")
        return redirect("panel:events")
    external = bool(event and event.is_external)
    form_class = ExternalEventForm if external else EventForm
    form = form_class(request.POST or None, request.FILES or None, instance=event)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if not obj.pk:
            obj.created_by = request.user
        obj.save()
        messages.success(request, "Evento guardado.")
        return redirect("panel:event_registrations", pk=obj.pk)
    return render(request, "panel/event_form.html", {"form": form, "event": event, "external": external})


@staff_required
@require_POST
def events_sync(request):
    from apps.events import etk

    try:
        result = etk.sync_events()
    except etk.EtkError as exc:
        messages.error(request, f"Não foi possível sincronizar com a ETK: {exc}")
    else:
        messages.success(request, f"ETK sincronizada: {result}.")
    return redirect("panel:events")


@staff_required
@require_POST
def event_delete(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if event.registrations.filter(status=Registration.Status.CONFIRMED).exists():
        event.is_published = False
        event.save(update_fields=["is_published"])
        messages.info(request, "O evento tem inscrições — foi despublicado em vez de apagado.")
    else:
        event.delete()
        messages.success(request, "Evento apagado.")
    return redirect("panel:events")


@staff_required
def event_registrations(request, pk):
    event = get_object_or_404(Event.objects.with_counts(), pk=pk)
    regs = event.registrations.select_related("user").order_by("status", "user__first_name")
    q = request.GET.get("q", "").strip()
    if q:
        regs = regs.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
                           | Q(user__member_number__icontains=q) | Q(user__email__icontains=q))
    if request.GET.get("formato") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="inscritos-{event.slug}.csv"'
        response.write("﻿")
        writer = csv.writer(response)
        writer.writerow(["Nº sócio", "Nome", "Email", "Telemóvel", "Distância", "Estado", "Presença", "Inscrito em"])
        for r in regs:
            writer.writerow([r.user.member_number, r.user.display_name, r.user.email, r.user.phone, r.distance,
                             r.get_status_display(), "sim" if r.checked_in_at else "não",
                             timezone.localtime(r.created_at).strftime("%Y-%m-%d %H:%M")])
        return response
    checked_in = event.registrations.filter(checked_in_at__isnull=False).count()
    return render(request, "panel/event_registrations.html", {
        "event": event, "registrations": regs, "q": q, "checked_in": checked_in,
    })


@staff_required
@require_POST
def registration_checkin(request, pk):
    reg = get_object_or_404(Registration.objects.select_related("event", "user"), pk=pk)
    if reg.checked_in_at:
        event_services.undo_check_in(reg)
        messages.info(request, f"Presença de {reg.user.display_name} removida.")
    elif event_services.check_in(reg):
        messages.success(request, f"Presença de {reg.user.display_name} confirmada (+{reg.event.effective_checkin_points} pts).")
    next_url = request.POST.get("next")
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect("panel:event_registrations", pk=reg.event_id)


# --- Moderação de corridas -------------------------------------------------------------
@staff_required
def runs(request):
    flt = request.GET.get("filtro", "suspeitas")
    qs = Run.objects.select_related("user").order_by("-created_at")
    if flt == "suspeitas":
        # Ritmo < 3:30/km ou distância > 42,2 km merecem uma segunda olhada
        qs = qs.filter(Q(pace_sec_per_km__lt=210) | Q(distance_km__gt=42.2))
    elif flt == "invalidas":
        qs = qs.filter(is_valid=False)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "panel/runs.html", {"page": page, "filtro": flt})


@staff_required
@require_POST
def run_toggle_valid(request, pk):
    run = get_object_or_404(Run, pk=pk)
    activity.set_run_validity(run, not run.is_valid, request.POST.get("note", ""))
    messages.success(request, "Corrida " + ("revalidada — pontos repostos." if run.is_valid else "invalidada — pontos removidos."))
    next_url = request.POST.get("next", "")
    return redirect(next_url if next_url.startswith("/") and not next_url.startswith("//") else "panel:runs")


# --- Subscrições -----------------------------------------------------------------------
@staff_required
def subscriptions(request):
    status = request.GET.get("estado", "pending")
    qs = Subscription.objects.select_related("user", "plan")
    if status in Subscription.Status.values:
        qs = qs.filter(status=status)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "panel/subscriptions.html", {
        "page": page, "status": status, "statuses": Subscription.Status.choices, "form": ActivateSubscriptionForm(),
    })


@staff_required
@require_POST
def subscription_activate(request, pk):
    sub = get_object_or_404(Subscription.objects.select_related("plan", "user"), pk=pk)
    form = ActivateSubscriptionForm(request.POST)
    if form.is_valid() and sub.status in (Subscription.Status.PENDING, Subscription.Status.EXPIRED, Subscription.Status.CANCELLED):
        sub.activate(by=request.user, method=form.cleaned_data["payment_method"],
                     reference=form.cleaned_data["payment_reference"])
        messages.success(request, f"Subscrição de {sub.user.display_name} activada até {timezone.localtime(sub.ends_at):%d/%m/%Y}.")
    else:
        messages.error(request, "Não foi possível activar esta subscrição.")
    return redirect("panel:subscriptions")


@staff_required
@require_POST
def subscription_cancel(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    sub.status = Subscription.Status.CANCELLED
    sub.save(update_fields=["status", "updated_at"])
    messages.info(request, "Subscrição cancelada.")
    return redirect("panel:subscriptions")


# --- Loja ----------------------------------------------------------------------------------
@staff_required
def orders(request):
    status = request.GET.get("estado", "abertas")
    qs = Order.objects.select_related("user", "pickup_event").prefetch_related("items")
    if status == "abertas":
        qs = qs.open()
    elif status in Order.Status.values:
        qs = qs.filter(status=status)
    event_id = request.GET.get("evento")
    if event_id and event_id.isdigit():
        qs = qs.filter(pickup_event_id=int(event_id))
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "panel/orders.html", {
        "page": page, "status": status, "statuses": Order.Status.choices, "methods": Order.Method.choices,
    })


@staff_required
@require_POST
def order_action(request, pk):
    order = get_object_or_404(Order, pk=pk)
    action = request.POST.get("action")
    try:
        if action == "paid":
            shop_services.mark_paid(order, request.POST.get("payment_method") or Order.Method.MPESA_MANUAL,
                                    request.POST.get("payment_reference", "")[:80])
            messages.success(request, f"Encomenda {order.number} marcada como paga.")
        elif action == "ready":
            shop_services.advance(order, Order.Status.READY)
            messages.success(request, f"Encomenda {order.number} pronta — o membro foi avisado por email.")
        elif action == "completed":
            shop_services.advance(order, Order.Status.COMPLETED)
            messages.success(request, f"Encomenda {order.number} entregue.")
        elif action == "cancel":
            shop_services.cancel_order(order, reason=f"cancelada por {request.user.email}")
            messages.info(request, f"Encomenda {order.number} cancelada e stock devolvido.")
        else:
            messages.error(request, "Acção desconhecida.")
    except shop_services.ShopError as exc:
        messages.error(request, str(exc))
    next_url = request.POST.get("next", "")
    return redirect(next_url if next_url.startswith("/") and not next_url.startswith("//") else "panel:orders")


# --- Entrada de bilhetes da ETK -----------------------------------------------------------------
@require_POST
def ticket_scan(request):
    """Leitor de QR à porta: bilhete `TCKT…|assinatura` → entrada na ETK + presença/pontos do membro. Responde em JSON."""
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({"result": "error", "message": "Sem permissão."}, status=403)
    outcome = ticket_checkin.check_in_by_qr(request.POST.get("qrValue", ""))
    return JsonResponse(outcome.as_dict())


@staff_required
@require_POST
def ticket_member_checkin(request, pk):
    """Staff leu o cartão do membro e escolheu o bilhete dele: dá a entrada pelo bilhete que a ETK tem."""
    member = get_object_or_404(User, pk=pk)
    outcome = ticket_checkin.check_in_member_ticket(member, request.POST.get("ticket_id", ""))
    text = f"{outcome.message} — {member.display_name}" + (f" (+{outcome.points} pts)" if outcome.points else "")
    (messages.success if outcome.admitted else messages.error)(request, text)
    return redirect(member.get_verify_url())
