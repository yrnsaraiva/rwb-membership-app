from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("", views.plans, name="plans"),
    path("pedir/<slug:slug>/", views.request_subscription, name="request"),
    path("pedido/<int:pk>/cancelar/", views.cancel_request, name="cancel_request"),
]
