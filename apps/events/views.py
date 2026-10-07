import re
from datetime import timedelta
from datetime import timezone as dt_timezone

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .models import Event, Registration


def distance_options(event):
    return [d.strip() for d in re.split(r"[·,;/|]", event.distances or "") if d.strip()]


def event_list(request):
    tab = request.GET.get("tab", "proximos")
    kind = request.GET.get("tipo", "")
    qs = Event.objects.past() if tab == "passados" else Event.objects.upcoming()
    if kind in Event.Kind.values:
        qs = qs.filter(kind=kind)
    page = Paginator(qs.with_counts(), 12).get_page(request.GET.get("page"))
    my_event_ids = set()
    if request.user.is_authenticated:
        my_event_ids = set(
            Registration.objects.filter(user=request.user, status=Registration.Status.CONFIRMED).values_list("event_id", flat=True)
        )
    return render(request, "events/list.html", {
        "page": page, "tab": tab, "kind": kind, "kinds": Event.Kind.choices, "my_event_ids": my_event_ids,
    })


def event_detail(request, slug):
    qs = Event.objects.with_counts()
    if not (request.user.is_authenticated and request.user.is_staff):
        qs = qs.filter(is_published=True)
    event = get_object_or_404(qs, slug=slug)
    registration = None
    if request.user.is_authenticated:
        registration = Registration.objects.filter(event=event, user=request.user).first()
    return render(request, "events/detail.html", {
        "event": event,
        "registration": registration,
        "distances": distance_options(event),
    })


@login_required
@require_POST
def event_register(request, slug):
    event = get_object_or_404(Event.objects.published(), slug=slug)
    distance = request.POST.get("distance", "")[:20]
    options = distance_options(event)
    if options and distance not in options:
        distance = options[0]
    try:
        services.register(request.user, event, distance)
    except services.RegistrationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Inscrição confirmada! Enviámos os detalhes para o teu email.")
    return redirect(event.get_absolute_url())


@login_required
@require_POST
def event_cancel(request, slug):
    event = get_object_or_404(Event.objects.published(), slug=slug)
    try:
        services.cancel(request.user, event)
    except services.RegistrationError as exc:
        messages.error(request, str(exc))
    else:
        messages.info(request, "Inscrição cancelada. A tua vaga ficou livre para outro membro.")
    return redirect(event.get_absolute_url())


def event_ics(request, slug):
    """Ficheiro .ics para adicionar o evento ao calendário do telemóvel."""
    event = get_object_or_404(Event.objects.published(), slug=slug)
    fmt = "%Y%m%dT%H%M%SZ"
    start = event.starts_at.astimezone(dt_timezone.utc)
    end = (event.ends_at or event.starts_at + timedelta(hours=2)).astimezone(dt_timezone.utc)

    def esc(text):
        return (text or "").replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")

    body = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//RunWithBroto//PT", "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:event-{event.pk}@runwithbroto",
        f"DTSTAMP:{timezone.now().astimezone(dt_timezone.utc).strftime(fmt)}",
        f"DTSTART:{start.strftime(fmt)}",
        f"DTEND:{end.strftime(fmt)}",
        f"SUMMARY:{esc(event.title)}",
        f"LOCATION:{esc(event.location)}",
        f"DESCRIPTION:{esc(event.summary or event.description[:500])}",
        f"URL:{request.build_absolute_uri(event.get_absolute_url())}",
        "END:VEVENT", "END:VCALENDAR", "",
    ])
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{event.slug}.ics"'
    return response
