from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import User

admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


class RWBUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name")


class RWBUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = RWBUserChangeForm
    add_form = RWBUserCreationForm
    change_password_form = AdminPasswordChangeForm

    ordering = ["-date_joined"]
    list_display = ["member_number", "email", "first_name", "last_name", "phone", "is_active", "is_staff", "date_joined"]
    list_filter = ["is_active", "is_staff", "city"]
    search_fields = ["email", "first_name", "last_name", "member_number", "phone"]
    readonly_fields = ["member_number", "card_token", "last_login", "date_joined"]
    fieldsets = (
        (None, {"fields": ("email", "password", "member_number", "card_token")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name", "phone", "city", "date_of_birth", "bio", "avatar", "show_on_leaderboard")}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "password1", "password2")}),
    )

