from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services
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
    try:
        services.request_subscription(request.user, plan)
    except services.SubscriptionError as exc:
        messages.info(request, str(exc))
        return redirect("billing:plans")
    messages.success(request, "Pedido registado! O clube vai entrar em contacto para confirmar o pagamento.")
    return redirect("billing:plans")


@login_required
@require_POST
def cancel_request(request, pk):
    get_object_or_404(Subscription, pk=pk, user=request.user, status=Subscription.Status.PENDING)
    services.cancel_request(request.user, pk)
    messages.info(request, "Pedido cancelado.")
    return redirect("billing:plans")
