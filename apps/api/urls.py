from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "api"

router = DefaultRouter()
router.register("events", views.EventViewSet, basename="event")
router.register("runs", views.RunViewSet, basename="run")
router.register("points", views.PointViewSet, basename="point")

urlpatterns = [
    path("auth/token/", views.TokenView.as_view(), name="token"),
    path("me/", views.me, name="me"),
    path("me/dashboard/", views.dashboard, name="dashboard"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("", include(router.urls)),
]
