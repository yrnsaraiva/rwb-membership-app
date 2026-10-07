from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Event, Registration


class RegistrationInline(TabularInline):
    model = Registration
    extra = 0
    fields = ["user", "status", "distance", "checked_in_at", "created_at"]
    readonly_fields = ["created_at"]
    autocomplete_fields = ["user"]
    tab = True


@admin.register(Event)
class EventAdmin(ModelAdmin):
    list_display = ["title", "kind", "starts_at", "location", "capacity", "is_published"]
    list_filter = ["kind", "is_published"]
    search_fields = ["title", "location"]
    prepopulated_fields = {"slug": ["title"]}
    date_hierarchy = "starts_at"
    inlines = [RegistrationInline]
    fieldsets = (
        (None, {"fields": ("title", "slug", "kind", "summary", "description", "cover", "is_published")}),
        ("Quando e onde", {"fields": ("starts_at", "ends_at", "location", "meeting_point", "map_url", "distances")}),
        ("Inscrições", {"fields": ("capacity", "registration_opens_at", "registration_closes_at", "price_mzn",
                                   "members_only", "checkin_points")}),
    )


@admin.register(Registration)
class RegistrationAdmin(ModelAdmin):
    list_display = ["event", "user", "status", "distance", "checked_in_at", "created_at"]
    list_filter = ["status", "event"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "event__title"]
    autocomplete_fields = ["user", "event"]
