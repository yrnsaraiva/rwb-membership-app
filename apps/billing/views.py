from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.emails import notify_staff

from .models import Plan, Subscription


def plans(request):
    context = {"plans": Plan.objects.filter(is_active=True)}
    if request.user.is_authenticated:
        subs = Subscription.objects.filter(user=request.user).select_related("plan")
        context["current"] = subs.active().order_by("-ends_at").first()
        context["pending"] = subs.pending().first()
        context["history"] = subs[:10]
    return render(request, "billing/plans.html", context)


@login_required
@require_POST
def request_subscription(request, slug):
    plan = get_object_or_404(Plan, slug=slug, is_active=True)
    if Subscription.objects.pending().filter(user=request.user).exists():
        messages.info(request, "Já tens um pedido pendente. O clube vai confirmá-lo em breve.")
        return redirect("billing:plans")
    sub = Subscription.objects.create(user=request.user, plan=plan, amount_mzn=plan.price_mzn)
    notify_staff(
        f"Novo pedido de subscrição: {request.user.display_name}",
        f"{request.user.display_name} ({request.user.member_number}, {request.user.phone or request.user.email}) "
        f"pediu o plano {plan.name} — {plan.price_mzn} MZN. Pedido #{sub.pk}.",
    )
    messages.success(request, "Pedido registado! O clube vai entrar em contacto para confirmar o pagamento.")
    return redirect("billing:plans")


@login_required
@require_POST
def cancel_request(request, pk):
    sub = get_object_or_404(Subscription, pk=pk, user=request.user, status=Subscription.Status.PENDING)
    sub.status = Subscription.Status.CANCELLED
    sub.save(update_fields=["status", "updated_at"])
    messages.info(request, "Pedido cancelado.")
    return redirect("billing:plans")
