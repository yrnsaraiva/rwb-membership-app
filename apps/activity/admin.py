from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import PointTransaction, Run


@admin.register(Run)
class RunAdmin(ModelAdmin):
    list_display = ["user", "date", "distance_km", "duration", "pace_sec_per_km", "is_valid", "created_at"]
    list_filter = ["is_valid", "date"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "title"]
    autocomplete_fields = ["user", "event"]
    date_hierarchy = "date"


@admin.register(PointTransaction)
class PointTransactionAdmin(ModelAdmin):
    list_display = ["user", "amount", "reason", "description", "created_at"]
    list_filter = ["reason"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "description"]
    autocomplete_fields = ["user"]
    raw_id_fields = ["run", "registration"]
