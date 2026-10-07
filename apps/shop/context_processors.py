from .cart import SESSION_KEY


def cart(request):
    raw = request.session.get(SESSION_KEY) if hasattr(request, "session") else None
    try:
        count = sum(int(v) for v in (raw or {}).values())
    except (TypeError, ValueError):
        count = 0
    return {"cart_count": count}
