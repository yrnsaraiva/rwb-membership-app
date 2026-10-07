from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.emails import send_templated_email

from . import ratelimit
from .forms import LoginForm, ProfileForm, RegisterForm
from .models import User
from .qr import member_qr_svg


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("activity:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="apps.accounts.backends.EmailBackend")
        send_templated_email("welcome", user.email, {"user": user})
        messages.success(request, f"Bem-vindo ao clube, {user.first_name}! O teu número de sócio é {user.member_number}.")
        return redirect("activity:dashboard")
    return render(request, "accounts/register.html", {"form": form})


class RateLimitedLoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        email = request.POST.get("username", "")
        if ratelimit.is_blocked(request, email):
            form = self.get_form()
            form.errors.clear()
            form.add_error(None, "Demasiadas tentativas falhadas. Aguarda alguns minutos e tenta novamente.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        ratelimit.reset(self.request, form.cleaned_data.get("username", ""))
        return super().form_valid(form)

    def form_invalid(self, form):
        ratelimit.register_failure(self.request, self.request.POST.get("username", ""))
        return super().form_invalid(form)


@login_required
def profile(request):
    from apps.activity.services import member_stats

    return render(request, "accounts/profile.html", {"stats": member_stats(request.user)})


@login_required
@require_http_methods(["GET", "POST"])
def profile_edit(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Perfil actualizado.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile_edit.html", {"form": form})


@login_required
def card(request):
    return render(request, "accounts/card.html", {"qr_svg": member_qr_svg(request.user)})


@login_required
@require_POST
def card_regenerate(request):
    request.user.regenerate_card_token()
    messages.success(request, "Novo QR gerado. O cartão anterior deixou de funcionar.")
    return redirect("accounts:card")


def verify(request, token):
    """Página aberta ao ler o QR do cartão: confirma que o sócio existe e está activo."""
    member = get_object_or_404(User, card_token=token)
    context = {"member": member}
    if request.user.is_authenticated and request.user.is_staff:
        # Staff a ler o QR à porta do evento: mostra as inscrições de hoje para marcar presença
        from datetime import timedelta

        from django.utils import timezone

        from apps.events.models import Registration

        now = timezone.now()
        context["today_registrations"] = Registration.objects.filter(
            user=member, status=Registration.Status.CONFIRMED,
            event__starts_at__gte=now - timedelta(hours=12), event__starts_at__lte=now + timedelta(hours=12),
        ).select_related("event")
    return render(request, "accounts/verify.html", context)


password_reset = auth_views.PasswordResetView.as_view(
    template_name="accounts/password_reset_form.html",
    email_template_name="emails/password_reset.txt",
    html_email_template_name="emails/password_reset.html",
    subject_template_name="emails/password_reset_subject.txt",
    success_url=reverse_lazy("accounts:password_reset_done"),
)
password_reset_done = auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html")
password_reset_confirm = auth_views.PasswordResetConfirmView.as_view(
    template_name="accounts/password_reset_confirm.html",
    success_url=reverse_lazy("accounts:password_reset_complete"),
)
password_reset_complete = auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html")
