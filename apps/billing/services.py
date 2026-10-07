"""Regras de negócio do premium (partilhadas pelas views web e pela API)."""
from apps.core.emails import notify_staff

from .models import Subscription


class SubscriptionError(Exception):
    pass


def request_subscription(user, plan) -> Subscription:
    if Subscription.objects.pending().filter(user=user).exists():
        raise SubscriptionError("Já tens um pedido pendente. O clube vai confirmá-lo em breve.")
    sub = Subscription.objects.create(user=user, plan=plan, amount_mzn=plan.price_mzn)
    notify_staff(
        f"Novo pedido de subscrição: {user.display_name}",
        f"{user.display_name} ({user.member_number}, {user.phone or user.email}) "
        f"pediu o plano {plan.name} — {plan.price_mzn} MZN. Pedido #{sub.pk}.",
    )
    return sub


def cancel_request(user, pk) -> Subscription:
    try:
        sub = Subscription.objects.get(pk=pk, user=user, status=Subscription.Status.PENDING)
    except Subscription.DoesNotExist:
        raise SubscriptionError("Pedido não encontrado ou já processado.") from None
    sub.status = Subscription.Status.CANCELLED
    sub.save(update_fields=["status", "updated_at"])
    return sub
