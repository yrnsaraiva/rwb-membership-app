from django import forms
from django.utils import timezone

from apps.events.models import Event

from .models import Order


class CheckoutForm(forms.Form):
    fulfilment = forms.ChoiceField(label="Como queres receber?", choices=Order.Fulfilment.choices,
                                   initial=Order.Fulfilment.EVENT, widget=forms.RadioSelect)
    pickup_event = forms.ModelChoiceField(label="Em que evento levantas?", queryset=Event.objects.none(), required=False,
                                          empty_label="Escolhe um evento")
    customer_name = forms.CharField(label="Nome", max_length=120)
    phone = forms.CharField(label="Telemóvel (M-Pesa)", max_length=20,
                            widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel", "placeholder": "+258 84 000 0000"}))
    delivery_address = forms.CharField(label="Morada de entrega", required=False,
                                       widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Bairro, rua, nº, referência"}))
    notes = forms.CharField(label="Notas (opcional)", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pickup_event"].queryset = Event.objects.filter(
            pk__in=[e.pk for e in Event.objects.upcoming()[:10]]
        ).order_by("starts_at")
        self.fields["pickup_event"].label_from_instance = lambda e: f"{e.title} — {timezone.localtime(e.starts_at):%d/%m %H:%M}"
        if user is not None and not self.is_bound:
            self.initial.setdefault("customer_name", user.get_full_name())
            self.initial.setdefault("phone", user.phone)

    def clean(self):
        cleaned = super().clean()
        f = cleaned.get("fulfilment")
        if f == Order.Fulfilment.EVENT and not cleaned.get("pickup_event"):
            self.add_error("pickup_event", "Escolhe o evento onde vais levantar.")
        if f == Order.Fulfilment.DELIVERY and not (cleaned.get("delivery_address") or "").strip():
            self.add_error("delivery_address", "Indica a morada de entrega.")
        return cleaned
