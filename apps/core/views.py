import json

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from apps.events.models import Event
from apps.leaderboard.services import get_leaderboard


def home(request):
    if request.user.is_authenticated and not request.GET.get("landing"):
        return redirect("activity:dashboard")
    return render(request, "core/home.html", {
        "events": Event.objects.upcoming().with_counts()[:3],
        "top": get_leaderboard("mes", "km", 5),
    })


def offline(request):
    return render(request, "core/offline.html")


@require_GET
@cache_control(max_age=86400)
def manifest(request):
    data = {
        "name": "RunWithBroto",
        "short_name": "RWB",
        "id": "/",
        "categories": ["sports", "health", "lifestyle"],
        "description": "Clube de corrida RunWithBroto — eventos, corridas, pontos e ranking.",
        "lang": "pt-MZ",
        "start_url": "/atividade/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#0B0B0B",
        "theme_color": "#0B0B0B",
        "icons": [
            {"src": static("img/icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("img/icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("img/icons/icon-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "Registar corrida", "url": "/atividade/corridas/nova/"},
            {"name": "Eventos", "url": "/eventos/"},
            {"name": "Cartão de membro", "url": "/conta/cartao/"},
        ],
    }
    return HttpResponse(json.dumps(data, ensure_ascii=False), content_type="application/manifest+json")


@require_GET
def service_worker(request):
    response = render(request, "core/sw.js", {
        "version": getattr(settings, "RELEASE", "v1"),
        "css_url": static("css/app.css"),
        "js_url": static("js/app.js"),
        "pwa_url": static("js/pwa.js"),
        "components_url": static("css/components.css"),
        "icon_url": static("img/icons/icon-192.png"),
    }, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /painel/\nDisallow: /django-admin/\nDisallow: /api/\n",
                        content_type="text/plain")


def healthz(request):
    """Endpoint de saúde para o Railway (verifica a ligação à base de dados)."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:  # noqa: BLE001
        return JsonResponse({"status": "db_error"}, status=503)
