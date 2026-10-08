from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from apps.events.webhooks import etk_webhook

admin.site.index_title = "Gestão do clube"

urlpatterns = [
    path("", include("apps.core.urls")),
    path("conta/", include("apps.accounts.urls")),
    path("eventos/", include("apps.events.urls")),
    path("atividade/", include("apps.activity.urls")),
    path("ranking/", include("apps.leaderboard.urls")),
    path("premium/", include("apps.billing.urls")),
    path("loja/", include("apps.shop.urls")),
    path("painel/", include("apps.panel.urls")),
    path("api/v1/", include("apps.api.urls")),
    path("webhooks/etk/", etk_webhook, name="etk_webhook"),
    path("django-admin/", admin.site.urls),
]

if settings.DEBUG or settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
