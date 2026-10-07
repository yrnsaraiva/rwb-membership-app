from django.urls import path

from . import views

app_name = "panel"

urlpatterns = [
    path("", views.index, name="index"),
    path("membros/", views.members, name="members"),
    path("membros/<int:pk>/", views.member_detail, name="member_detail"),
    path("membros/<int:pk>/estado/", views.member_toggle_active, name="member_toggle_active"),
    path("eventos/", views.events, name="events"),
    path("eventos/novo/", views.event_form, name="event_create"),
    path("eventos/<int:pk>/editar/", views.event_form, name="event_edit"),
    path("eventos/<int:pk>/apagar/", views.event_delete, name="event_delete"),
    path("eventos/<int:pk>/inscritos/", views.event_registrations, name="event_registrations"),
    path("inscricoes/<int:pk>/presenca/", views.registration_checkin, name="registration_checkin"),
    path("corridas/", views.runs, name="runs"),
    path("corridas/<int:pk>/validade/", views.run_toggle_valid, name="run_toggle_valid"),
    path("encomendas/", views.orders, name="orders"),
    path("encomendas/<int:pk>/accao/", views.order_action, name="order_action"),
    path("subscricoes/", views.subscriptions, name="subscriptions"),
    path("subscricoes/<int:pk>/activar/", views.subscription_activate, name="subscription_activate"),
    path("subscricoes/<int:pk>/cancelar/", views.subscription_cancel, name="subscription_cancel"),
]
