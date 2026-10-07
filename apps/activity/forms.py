from datetime import timedelta
from decimal import Decimal

from django import forms
from django.conf import settings
from django.utils import timezone

from apps.events.models import Event, Registration

from .services import run_limit_error

MAX_BACKDATE_DAYS = 60


class RunForm(forms.Form):
    date = forms.DateField(label="Data", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    distance_km = forms.DecimalField(label="Distância (km)", max_digits=6, decimal_places=2, min_value=Decimal("0.1"),
                                     widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal", "placeholder": "5.00"}))
    hours = forms.IntegerField(label="h", min_value=0, max_value=23, initial=0, required=False,
                               widget=forms.NumberInput(attrs={"inputmode": "numeric", "placeholder": "0"}))
    minutes = forms.IntegerField(label="min", min_value=0, max_value=59, required=False,
                                 widget=forms.NumberInput(attrs={"inputmode": "numeric", "placeholder": "30"}))
    seconds = forms.IntegerField(label="s", min_value=0, max_value=59, required=False,
                                 widget=forms.NumberInput(attrs={"inputmode": "numeric", "placeholder": "00"}))
    title = forms.CharField(label="Título (opcional)", max_length=80, required=False,
                            widget=forms.TextInput(attrs={"placeholder": "Corrida matinal na Marginal"}))
    event = forms.ModelChoiceField(label="Evento associado (opcional)", queryset=Event.objects.none(), required=False,
                                   empty_label="— Nenhum —")
    notes = forms.CharField(label="Notas", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["date"].initial = timezone.localdate()
        if user is not None:
            recent = timezone.now() - timedelta(days=MAX_BACKDATE_DAYS)
            self.fields["event"].queryset = Event.objects.filter(
                registrations__user=user,
                registrations__status=Registration.Status.CONFIRMED,
                starts_at__gte=recent,
                starts_at__lte=timezone.now() + timedelta(days=1),
            ).distinct()

    def clean_date(self):
        d = self.cleaned_data["date"]
        t = timezone.localdate()
        if d > t:
            raise forms.ValidationError("Não podes registar corridas no futuro.")
        if d < t - timedelta(days=MAX_BACKDATE_DAYS):
            raise forms.ValidationError(f"Só é possível registar corridas dos últimos {MAX_BACKDATE_DAYS} dias.")
        return d

    def clean_distance_km(self):
        km = self.cleaned_data["distance_km"]
        if km > settings.RWB_MAX_RUN_KM:
            raise forms.ValidationError(f"Distância máxima por corrida: {settings.RWB_MAX_RUN_KM} km.")
        return km

    def clean(self):
        cleaned = super().clean()
        h = cleaned.get("hours") or 0
        m = cleaned.get("minutes") or 0
        s = cleaned.get("seconds") or 0
        duration = timedelta(hours=h, minutes=m, seconds=s)
        if duration.total_seconds() <= 0:
            raise forms.ValidationError("Indica a duração da corrida.")
        km = cleaned.get("distance_km")
        if km:
            pace = duration.total_seconds() / float(km)
            if pace < settings.RWB_MIN_PACE_SEC_PER_KM:
                raise forms.ValidationError("Ritmo demasiado rápido para ser real — confirma a distância e o tempo.")
        d = cleaned.get("date")
        if self.user is not None and km and d:
            error = run_limit_error(self.user, date=d, distance_km=km, duration=duration)
            if error:
                raise forms.ValidationError(error)
        cleaned["duration"] = duration
        return cleaned
