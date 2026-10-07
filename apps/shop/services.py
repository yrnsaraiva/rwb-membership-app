"""Regras de negócio da loja: reserva de stock, encomendas e estados."""
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.emails import notify_staff, send_templated_email
from apps.notifications import services as push

from .models import Order, OrderItem, ProductVariant


class ShopError(Exception):
    pass


@transaction.atomic
def place_order(user, cart, *, fulfilment, customer_name, phone, delivery_address="", notes="", pickup_event=None):
    if not cart.data:
        raise ShopError("O carrinho está vazio.")
    ids = [int(k) for k in cart.data]
    # Bloqueia as variantes para que duas pessoas não comprem a última unidade ao mesmo tempo
    variants = {v.pk: v for v in ProductVariant.objects.select_for_update().select_related("product").filter(
        pk__in=ids, is_active=True, product__is_active=True)}
    if len(variants) != len(ids):
        raise ShopError("Alguns artigos deixaram de estar disponíveis. Revê o carrinho.")

    items, subtotal, total_items = [], Decimal("0"), Decimal("0")
    for key, qty in cart.data.items():
        v = variants[int(key)]
        if qty > v.stock:
            left = f"só há {v.stock}" if v.stock else "esgotou"
            raise ShopError(f"{v.product.name} ({v.name}): {left}.")
        unit = v.unit_price_for(user)
        subtotal += v.price_mzn * qty
        total_items += unit * qty
        items.append((v, qty, unit))

    delivery_fee = Decimal(settings.RWB_SHOP_DELIVERY_FEE) if fulfilment == Order.Fulfilment.DELIVERY else Decimal("0")
    order = Order.objects.create(
        user=user, fulfilment=fulfilment, pickup_event=pickup_event if fulfilment == Order.Fulfilment.EVENT else None,
        customer_name=customer_name, phone=phone,
        delivery_address=delivery_address if fulfilment == Order.Fulfilment.DELIVERY else "",
        notes=notes, subtotal_mzn=subtotal, discount_mzn=subtotal - total_items, delivery_fee_mzn=delivery_fee,
        total_mzn=total_items + delivery_fee,
    )
    for v, qty, unit in items:
        OrderItem.objects.create(order=order, variant=v, product_name=v.product.name, variant_name=v.name,
                                 unit_price_mzn=unit, list_price_mzn=v.price_mzn, quantity=qty)
        ProductVariant.objects.filter(pk=v.pk).update(stock=F("stock") - qty)
    cart.clear()

    def _notify():
        send_templated_email("order_placed", user.email, {"order": order, "user": user,
                                                           "payment": payment_instructions()})
        notify_staff(f"Nova encomenda {order.number} — {order.total_mzn:.0f} MZN",
                     f"{order.customer_name} ({user.member_number}, {order.phone}) fez a encomenda {order.number}: "
                     + ", ".join(f"{q}× {v.product.name} {v.name}" for v, q, _ in items)
                     + f". Entrega: {order.get_fulfilment_display()}.")
    transaction.on_commit(_notify)
    return order


def _restock(order):
    for item in order.items.select_related("variant"):
        if item.variant_id:
            ProductVariant.objects.filter(pk=item.variant_id).update(stock=F("stock") + item.quantity)


@transaction.atomic
def cancel_order(order, reason=""):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status in (Order.Status.CANCELLED, Order.Status.COMPLETED):
        raise ShopError("Esta encomenda já não pode ser cancelada.")
    _restock(order)
    order.status = Order.Status.CANCELLED
    order.cancelled_at = timezone.now()
    if reason:
        order.staff_notes = (order.staff_notes + f"\n[{timezone.localtime():%d/%m %H:%M}] Cancelada: {reason}").strip()
    order.save()
    return order


@transaction.atomic
def mark_paid(order, method=Order.Method.MPESA_MANUAL, reference=""):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.PENDING:
        raise ShopError("Só encomendas a aguardar pagamento podem ser marcadas como pagas.")
    order.status = Order.Status.PAID
    order.payment_method = method
    order.payment_reference = reference
    order.paid_at = timezone.now()
    order.save()
    transaction.on_commit(lambda: send_templated_email("order_status", order.user.email, {"order": order, "user": order.user}))
    push.notify(order.user, f"Pagamento recebido — {order.number}", "A tua encomenda está a ser preparada.",
                url=order.get_absolute_url(), tag=f"order-{order.pk}")
    return order


@transaction.atomic
def advance(order, status):
    """Avança para 'pronto' ou 'entregue'."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    allowed = {Order.Status.READY: [Order.Status.PAID], Order.Status.COMPLETED: [Order.Status.PAID, Order.Status.READY]}
    if status not in allowed or order.status not in allowed[status]:
        raise ShopError("Mudança de estado inválida.")
    order.status = status
    if status == Order.Status.COMPLETED:
        order.completed_at = timezone.now()
    order.save()
    if status == Order.Status.READY:
        transaction.on_commit(lambda: send_templated_email("order_status", order.user.email, {"order": order, "user": order.user}))
        push.notify(order.user, f"Encomenda {order.number} pronta", "Já podes levantar ou receber a tua encomenda.",
                    url=order.get_absolute_url(), tag=f"order-{order.pk}")
    return order


def payment_instructions():
    return {
        "mpesa_number": settings.RWB_SHOP_MPESA_NUMBER,
        "mpesa_name": settings.RWB_SHOP_MPESA_NAME,
        "bank_details": settings.RWB_SHOP_BANK_DETAILS,
        "hold_days": settings.RWB_SHOP_HOLD_DAYS,
    }
