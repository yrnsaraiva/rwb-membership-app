"""Regras de negócio de inscrições (vagas, cancelamento, presença)."""
from django.db import transaction
from django.utils import timezone

from apps.core.emails import send_templated_email

from .models import Event, Registration


class RegistrationError(Exception):
    pass


@transaction.atomic
def register(user, event: Event, distance: str = "") -> Registration:
    # Bloqueia a linha do evento para evitar overbooking em picos de inscrição (RNF-06)
    event = Event.objects.select_for_update().get(pk=event.pk)
    if not event.registration_is_open:
        raise RegistrationError("As inscrições para este evento não estão abertas.")
    if event.has_paid_ticket:
        raise RegistrationError("Este evento tem bilhete pago: a inscrição faz-se no site de bilhetes.")
    if event.members_only and not user.is_premium:
        raise RegistrationError("Este evento é exclusivo para membros premium.")

    existing = Registration.objects.select_for_update().filter(event=event, user=user).first()
    if existing and existing.is_active:
        raise RegistrationError("Já estás inscrito neste evento.")

    confirmed = Registration.objects.filter(event=event, status=Registration.Status.CONFIRMED).count()
    if event.capacity is not None and confirmed >= event.capacity:
        raise RegistrationError("Evento esgotado — não há vagas disponíveis.")

    if existing:
        existing.status = Registration.Status.CONFIRMED
        existing.cancelled_at = None
        existing.distance = distance
        existing.save(update_fields=["status", "cancelled_at", "distance"])
        registration = existing
    else:
        registration = Registration.objects.create(event=event, user=user, distance=distance)

    transaction.on_commit(lambda: send_templated_email(
        "registration_confirmed", user.email, {"user": user, "event": event, "registration": registration}
    ))
    return registration


@transaction.atomic
def cancel(user, event: Event) -> Registration:
    registration = Registration.objects.select_for_update().filter(
        event=event, user=user, status=Registration.Status.CONFIRMED
    ).first()
    if not registration:
        raise RegistrationError("Não tens inscrição activa neste evento.")
    if event.is_past:
        raise RegistrationError("Não é possível cancelar a inscrição num evento que já começou.")
    registration.status = Registration.Status.CANCELLED
    registration.cancelled_at = timezone.now()
    registration.save(update_fields=["status", "cancelled_at"])
    return registration


@transaction.atomic
def check_in(registration: Registration) -> bool:
    """Marca presença e atribui pontos. Devolve False se já tinha presença."""
    from apps.activity.models import PointTransaction

    registration = Registration.objects.select_for_update().select_related("event", "user").get(pk=registration.pk)
    if registration.checked_in_at or not registration.is_active:
        return False
    registration.checked_in_at = timezone.now()
    registration.save(update_fields=["checked_in_at"])
    points = registration.event.effective_checkin_points
    if points:
        PointTransaction.objects.create(
            user=registration.user,
            amount=points,
            reason=PointTransaction.Reason.EVENT_CHECKIN,
            registration=registration,
            description=f"Presença: {registration.event.title}",
        )
    return True


@transaction.atomic
def undo_check_in(registration: Registration) -> None:
    from apps.activity.models import PointTransaction

    registration = Registration.objects.select_for_update().get(pk=registration.pk)
    registration.checked_in_at = None
    registration.save(update_fields=["checked_in_at"])
    PointTransaction.objects.filter(registration=registration, reason=PointTransaction.Reason.EVENT_CHECKIN).delete()
