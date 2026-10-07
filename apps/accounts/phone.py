"""Números de telemóvel de Moçambique no formato que a ETK usa: 258XXXXXXXXX (12 dígitos)."""
import re


def normalize_phone(raw) -> str:
    """'+258 84 123 4567', '84 123 4567', '00258841234567' → '258841234567'. Vazio se não for um número moçambicano."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if re.fullmatch(r"2588[2-7]\d{7}", digits):  # telemóveis: 82/83 (Tmcel), 84/85 (Vodacom), 86/87 (Movitel)
        return digits
    if re.fullmatch(r"8[2-7]\d{7}", digits):
        return "258" + digits
    return ""
