from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(ModelAdmin):
    list_display = ["name", "price_mzn", "duration_days", "is_active", "is_featured", "order"]
    list_editable = ["is_active", "is_featured", "order"]
    prepopulated_fields = {"slug": ["name"]}


@admin.action(description="Activar subscrições seleccionadas")
def activate_selected(modeladmin, request, queryset):
    count = 0
    for sub in queryset.select_related("plan", "user"):
        if sub.status in (Subscription.Status.PENDING, Subscription.Status.EXPIRED):
            sub.activate(by=request.user)
            count += 1
    messages.success(request, f"{count} subscrição(ões) activada(s).")


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = ["user", "plan", "status", "amount_mzn", "payment_method", "starts_at", "ends_at", "created_at"]
    list_filter = ["status", "plan", "payment_method"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "payment_reference"]
    autocomplete_fields = ["user"]
    readonly_fields = ["activated_by", "created_at", "updated_at"]
    actions = [activate_selected]
