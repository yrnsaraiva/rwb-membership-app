from decimal import Decimal, InvalidOperation

from django import template

from apps.activity.services import format_duration, format_pace

register = template.Library()


@register.filter
def pace(seconds):
    """Segundos/km → 5:32"""
    return format_pace(seconds)


@register.filter
def duration(td):
    return format_duration(td)


@register.filter
def km(value, decimals=1):
    """Formata km à portuguesa: 12,5"""
    try:
        value = Decimal(value or 0)
    except (InvalidOperation, TypeError):
        return value
    text = f"{value:,.{int(decimals)}f}"
    return text.replace(",", " ").replace(".", ",")


@register.filter
def mzn(value):
    """1500 → 1 500,00 MZN"""
    try:
        value = Decimal(value or 0)
    except (InvalidOperation, TypeError):
        return value
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    if text.endswith(",00"):
        text = text[:-3]
    return f"{text} MZN"


@register.filter
def num(value):
    """Separador de milhares com espaço: 12 450"""
    try:
        return f"{int(value or 0):,}".replace(",", " ")
    except (TypeError, ValueError):
        return value


@register.simple_tag(takes_context=True)
def qs(context, **kwargs):
    """Mantém os parâmetros GET actuais, substituindo os indicados."""
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"
