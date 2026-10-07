"""Entrada de quem comprou bilhete na ETK: marca a entrada na ETK e dá a presença (e os pontos) ao membro RWB.

O membro é reconhecido pelo telemóvel do bilhete (258…) e, se não bater, pelo email. Só se atribui a um membro quando a
correspondência é única: dois membros com o mesmo número não recebem pontos por engano.
"""
import re
from dataclasses import dataclass

from django.contrib.auth import get_user_model

from apps.accounts.phone import normalize_phone

from . import etk
from .models import Registration

QR_PATTERN = re.compile(r"^TCKT\d+\|[0-9a-f]{16}$")
MESSAGES = {
    "ok": "Entrada autorizada",
    "already_entered": "Este bilhete já foi usado",
    "not_paid": "Bilhete sem pagamento confirmado",
    "not_found": "Bilhete não encontrado",
    "invalid_qr": "QR não reconhecido",
    "error": "Não foi possível falar com a ETK",
}


@dataclass
class Outcome:
    result: str
    message: str
    holder: str = ""
    event_title: str = ""
    member: object = None
    points: int = 0
    registered: bool = False

    @property
    def admitted(self):
        return self.result in ("ok", "already_entered")

    def as_dict(self):
        return {"result": self.result, "message": self.message, "holder": self.holder, "event": self.event_title,
                "member": {"name": self.member.display_name, "member_number": self.member.member_number} if self.member else None,
                "points": self.points, "registered": self.registered}


def find_member(phone="", email=""):
    """Membro activo com este telemóvel (ou, em alternativa, email) — só se for único."""
    User = get_user_model()
    normalized = normalize_phone(phone)
    if normalized:
        matches = list(User.objects.filter(phone_e164=normalized, is_active=True)[:2])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    if email:
        return User.objects.filter(email__iexact=email.strip(), is_active=True).first()
    return None


def check_in_by_qr(qr_value: str) -> Outcome:
    """Bilhete lido à porta (QR `TCKT…|assinatura`)."""
    qr_value = (qr_value or "").strip()
    if not QR_PATTERN.match(qr_value):
        return Outcome("invalid_qr", MESSAGES["invalid_qr"])
    try:
        res = etk.check_in_ticket(qr_value)
    except etk.EtkError:
        return Outcome("error", MESSAGES["error"])
    ticket = res["ticket"] or {}
    message = MESSAGES.get(res["result"], res["message"] or "Resultado desconhecido")
    if res["result"] == "not_paid" and ticket.get("payment") == "preregistered":
        message = "Pré-inscrição sem confirmação de presença"
    outcome = Outcome(res["result"], message,
                      holder=ticket.get("fullName") or "", event_title=(ticket.get("event") or {}).get("name", ""))
    if outcome.admitted:
        _attach_member(outcome, ticket)
    return outcome


def _attach_member(outcome: Outcome, ticket: dict):
    """Liga a entrada ao membro (se o titular o for): espelha o bilhete e, como já tem entrada, paga a presença uma só vez."""
    from . import tickets

    outcome.member = find_member(ticket.get("phone", ""), ticket.get("email", ""))
    if outcome.member is None or not ticket.get("id"):
        return
    already = Registration.objects.filter(external_ticket_id=ticket["id"], checked_in_at__isnull=False).exists()
    reg = tickets.upsert_registration({**ticket, "entered": True}, outcome.member)
    if reg is not None:
        outcome.registered = True
        if reg.checked_in_at and not already:
            outcome.points = reg.event.effective_checkin_points
