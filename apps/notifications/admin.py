from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(ModelAdmin):
    list_display = ("user", "user_agent", "created_at", "last_success_at", "failures")
    search_fields = ("user__email",)
    readonly_fields = ("user", "endpoint", "p256dh", "auth", "user_agent", "created_at", "last_success_at", "failures")

    def has_add_permission(self, request):
        return False
