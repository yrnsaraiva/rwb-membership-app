"""Re-regista o admin de tokens do DRF com o estilo do Unfold."""
from django.contrib import admin
from rest_framework.authtoken.admin import TokenAdmin as BaseTokenAdmin
from rest_framework.authtoken.models import TokenProxy
from unfold.admin import ModelAdmin

admin.site.unregister(TokenProxy)


@admin.register(TokenProxy)
class TokenAdmin(BaseTokenAdmin, ModelAdmin):
    pass
