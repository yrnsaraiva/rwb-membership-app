"""Carrinho em sessão (funciona também para visitantes; o checkout exige conta)."""
from decimal import Decimal

from django.conf import settings

from .models import ProductVariant

SESSION_KEY = "rwb_cart"
MAX_QTY_PER_LINE = 10


class Cart:
    def __init__(self, request):
        self.request = request
        self.session = request.session
        raw = self.session.get(SESSION_KEY) or {}
        self.data = {str(k): int(v) for k, v in raw.items() if str(k).isdigit() and int(v) > 0}

    def _save(self):
        self.session[SESSION_KEY] = self.data
        self.session.modified = True

    def add(self, variant_id, qty=1):
        key = str(variant_id)
        self.data[key] = min(self.data.get(key, 0) + int(qty), MAX_QTY_PER_LINE)
        self._save()

    def set(self, variant_id, qty):
        key = str(variant_id)
        qty = int(qty)
        if qty <= 0:
            self.data.pop(key, None)
        else:
            self.data[key] = min(qty, MAX_QTY_PER_LINE)
        self._save()

    def remove(self, variant_id):
        self.data.pop(str(variant_id), None)
        self._save()

    def clear(self):
        self.data = {}
        self._save()

    def quantity_of(self, variant_id):
        return self.data.get(str(variant_id), 0)

    @property
    def count(self):
        return sum(self.data.values())

    def __len__(self):
        return self.count

    def lines(self):
        """Linhas com preços calculados para o utilizador actual (desconto premium incluído)."""
        user = getattr(self.request, "user", None)
        variants = (
            ProductVariant.objects.filter(pk__in=[int(k) for k in self.data], is_active=True, product__is_active=True)
            .select_related("product").prefetch_related("product__images")
        )
        found = {str(v.pk): v for v in variants}
        # Remove do carrinho variantes que deixaram de estar à venda
        stale = [k for k in self.data if k not in found]
        if stale:
            for k in stale:
                self.data.pop(k)
            self._save()
        lines = []
        for key, qty in self.data.items():
            v = found[key]
            unit = v.unit_price_for(user)
            lines.append({
                "variant": v,
                "product": v.product,
                "quantity": qty,
                "list_price": v.price_mzn,
                "unit_price": unit,
                "line_total": unit * qty,
                "list_total": v.price_mzn * qty,
                "available": v.stock,
                "short": qty > v.stock,
            })
        return lines

    def summary(self, fulfilment=None):
        lines = self.lines()
        subtotal = sum((line["list_total"] for line in lines), Decimal("0"))
        total_items = sum((line["line_total"] for line in lines), Decimal("0"))
        delivery = Decimal(settings.RWB_SHOP_DELIVERY_FEE) if fulfilment == "delivery" and lines else Decimal("0")
        return {
            "lines": lines,
            "subtotal": subtotal,
            "discount": subtotal - total_items,
            "delivery_fee": delivery,
            "items_total": total_items,
            "total": total_items + delivery,
            "has_shortage": any(line["short"] for line in lines),
        }
