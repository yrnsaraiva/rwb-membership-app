from django.conf import settings
from django.contrib.staticfiles import finders


def _compiled_css_available():
    # Em desenvolvimento, se o CSS do Tailwind ainda não foi compilado, usa o CDN como fallback.
    if not settings.DEBUG:
        return True  # em produção o CSS é sempre compilado no build (Dockerfile)
    return bool(finders.find("css/app.css"))


def site(request):
    return {
        "SITE_NAME": settings.SITE_NAME,
        "SITE_URL": settings.SITE_URL,
        "CURRENCY": settings.CURRENCY,
        "TAILWIND_CDN_FALLBACK": not _compiled_css_available(),
        "nav": _active_nav(request),
        "VAPID_PUBLIC_KEY": settings.VAPID_PUBLIC_KEY,
        "ETK_ENABLED": settings.ETK_ENABLED,
        "points_per_km": settings.RWB_POINTS_PER_KM,
        "streak_every": settings.RWB_STREAK_BONUS_EVERY,
        "streak_bonus": settings.RWB_STREAK_BONUS_POINTS,
        "checkin_points": settings.RWB_EVENT_CHECKIN_POINTS,
    }


def _active_nav(request):
    path = request.path
    for prefix, name in [
        ("/atividade", "dashboard"),
        ("/eventos", "events"),
        ("/ranking", "leaderboard"),
        ("/conta", "profile"),
        ("/premium", "profile"),
        ("/painel", "panel"),
        ("/loja", "shop"),
    ]:
        if path.startswith(prefix):
            return name
    return "home"
