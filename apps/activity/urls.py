from django.urls import path

from . import views

app_name = "activity"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("corridas/", views.run_list, name="run_list"),
    path("corridas/nova/", views.run_create, name="run_create"),
    path("corridas/<int:pk>/apagar/", views.run_delete, name="run_delete"),
    path("pontos/", views.points_history, name="points"),
]
