from django import forms

from apps.billing.models import Subscription
from apps.events.models import Event


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%dT%H:%M", **kwargs)


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "title", "kind", "summary", "description", "cover",
            "starts_at", "ends_at", "location", "meeting_point", "map_url", "distances",
            "capacity", "registration_opens_at", "registration_closes_at",
            "price_mzn", "members_only", "checkin_points", "is_published",
        ]
        widgets = {
            "starts_at": DateTimeLocalInput(),
            "ends_at": DateTimeLocalInput(),
            "registration_opens_at": DateTimeLocalInput(),
            "registration_closes_at": DateTimeLocalInput(),
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ["starts_at", "ends_at", "registration_opens_at", "registration_closes_at"]:
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]

    def clean(self):
        cleaned = super().clean()
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            self.add_error("ends_at", "O fim tem de ser depois do início.")
        opens, closes = cleaned.get("registration_opens_at"), cleaned.get("registration_closes_at")
        if opens and closes and closes <= opens:
            self.add_error("registration_closes_at", "O fecho tem de ser depois da abertura.")
        if starts and closes and closes > starts:
            self.add_error("registration_closes_at", "As inscrições devem fechar antes do início do evento.")
        return cleaned


class PointsAdjustForm(forms.Form):
    amount = forms.IntegerField(label="Pontos (+/-)")
    description = forms.CharField(label="Motivo", max_length=160)

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount == 0:
            raise forms.ValidationError("Indica um valor diferente de zero.")
        return amount


class ActivateSubscriptionForm(forms.Form):
    payment_method = forms.ChoiceField(
        label="Método", choices=[c for c in Subscription.Method.choices if c[0] != Subscription.Method.MPESA_C2B]
    )
    payment_reference = forms.CharField(label="Referência / recibo", max_length=80, required=False)


class ExternalEventForm(forms.ModelForm):
    """Eventos vindos da ETK: nome, data, local e bilhetes são da ETK; aqui só se edita o que é específico do clube."""

    class Meta:
        model = Event
        fields = ["meeting_point", "map_url", "distances", "checkin_points", "members_only"]
