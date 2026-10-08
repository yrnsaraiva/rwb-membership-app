from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from . import views, views_account, views_shop, views_staff

app_name = "api"

router = DefaultRouter()
router.register("events", views.EventViewSet, basename="event")
router.register("runs", views.RunViewSet, basename="run")
router.register("points", views.PointViewSet, basename="point")
router.register("shop/products", views_shop.ProductViewSet, basename="product")
router.register("shop/orders", views_shop.OrderViewSet, basename="order")

urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
    path("auth/token/", views.TokenView.as_view(), name="token"),
    path("auth/logout/", views.logout, name="logout"),
    path("auth/register/", views_account.RegisterView.as_view(), name="register"),
    path("auth/password-reset/", views_account.PasswordResetView.as_view(), name="password_reset"),
    path("auth/password-reset/confirm/", views_account.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("me/password/", views_account.ChangePasswordView.as_view(), name="change_password"),
    path("push/config/", views_account.PushConfigView.as_view(), name="push_config"),
    path("me/push/", views_account.PushSubscriptionView.as_view(), name="push_subscription"),
    path("staff/cards/<uuid:token>/", views_staff.MemberCardView.as_view(), name="staff_card"),
    path("staff/registrations/<int:pk>/checkin/", views_staff.CheckInView.as_view(), name="staff_checkin"),
    path("staff/tickets/check-in/", views_staff.TicketCheckInView.as_view(), name="staff_ticket_checkin"),
    path("shop/config/", views_shop.ShopConfigView.as_view(), name="shop_config"),
    path("premium/plans/", views_shop.PlanListView.as_view(), name="plans"),
    path("premium/", views_shop.PremiumView.as_view(), name="premium"),
    path("premium/requests/<int:pk>/cancel/", views_shop.PremiumCancelView.as_view(), name="premium_cancel"),
    path("me/", views.me, name="me"),
    path("me/dashboard/", views.dashboard, name="dashboard"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("", include(router.urls)),
]
