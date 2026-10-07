from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("", views.product_list, name="list"),
    path("carrinho/", views.cart_view, name="cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("encomendas/", views.order_list, name="orders"),
    path("encomendas/<int:pk>/", views.order_detail, name="order"),
    path("encomendas/<int:pk>/cancelar/", views.order_cancel, name="order_cancel"),
    path("<slug:slug>/", views.product_detail, name="product"),
    path("<slug:slug>/adicionar/", views.cart_add, name="cart_add"),
]
