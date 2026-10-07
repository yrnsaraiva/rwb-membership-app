from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("registar/", views.register, name="register"),
    path("entrar/", views.RateLimitedLoginView.as_view(), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("perfil/", views.profile, name="profile"),
    path("perfil/editar/", views.profile_edit, name="profile_edit"),
    path("cartao/", views.card, name="card"),
    path("verificar/<uuid:token>/", views.verify, name="verify"),
    path("recuperar/", views.password_reset, name="password_reset"),
    path("recuperar/enviado/", views.password_reset_done, name="password_reset_done"),
    path("recuperar/<uidb64>/<token>/", views.password_reset_confirm, name="password_reset_confirm"),
    path("recuperar/concluido/", views.password_reset_complete, name="password_reset_complete"),
]
