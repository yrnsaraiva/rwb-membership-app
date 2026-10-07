"""Loja de merch e premium na API."""
from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing import services as billing_services
from apps.billing.models import Plan, Subscription
from apps.events.models import Event
from apps.shop import services as shop_services
from apps.shop.cart import MAX_QTY_PER_LINE
from apps.shop.models import Order, Product

from .serializers import (
    DetailSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    PlanSerializer,
    PremiumStatusSerializer,
    ProductSerializer,
    ShopConfigSerializer,
    SubscriptionCreateSerializer,
    SubscriptionSerializer,
)


class ItemsCart:
    """Carrinho sem sessão para a API: o cliente móvel envia as linhas no pedido."""

    def __init__(self, items):
        self.data = {}
        for item in items:
            key = str(item["variant"])
            self.data[key] = min(self.data.get(key, 0) + item["quantity"], MAX_QTY_PER_LINE)

    def clear(self):
        self.data = {}


@extend_schema(tags=["Loja"])
@extend_schema_view(
    list=extend_schema(summary="Catálogo", auth=[], parameters=[
        OpenApiParameter("categoria", str, description="`slug` da categoria.")]),
    retrieve=extend_schema(summary="Detalhe de um produto", auth=[]),
)
class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        qs = Product.objects.active().select_related("category").prefetch_related("images", "variants")
        cat = self.request.query_params.get("categoria")
        return qs.filter(category__slug=cat) if cat else qs


@extend_schema(tags=["Loja"], auth=[], responses=ShopConfigSerializer, summary="Taxas, desconto premium e instruções de pagamento")
class ShopConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        pay = shop_services.payment_instructions()
        events = Event.objects.upcoming().with_counts()[:10]
        return Response(ShopConfigSerializer({
            "delivery_fee_mzn": settings.RWB_SHOP_DELIVERY_FEE,
            "premium_discount_percent": settings.RWB_PREMIUM_SHOP_DISCOUNT,
            "hold_days": pay["hold_days"], "mpesa_number": pay["mpesa_number"], "mpesa_name": pay["mpesa_name"],
            "bank_details": pay["bank_details"], "pickup_events": events,
        }, context={"request": request}).data)


@extend_schema(tags=["Loja"])
@extend_schema_view(
    list=extend_schema(summary="As minhas encomendas"),
    retrieve=extend_schema(summary="Detalhe de uma encomenda"),
    create=extend_schema(summary="Fazer encomenda", request=OrderCreateSerializer,
                         description="Reserva o stock. O pagamento é feito fora da app (M-Pesa/transferência) com as "
                                     "instruções de `GET /shop/config/`; o clube confirma-o no painel.",
                         responses={201: OrderSerializer, 400: DetailSerializer}),
)
class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return Order.objects.filter(user=self.request.user).prefetch_related("items").select_related("pickup_event")

    def create(self, request, *args, **kwargs):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        form = d["form"].cleaned_data
        try:
            order = shop_services.place_order(
                request.user, ItemsCart(d["items"]), fulfilment=form["fulfilment"], customer_name=form["customer_name"],
                phone=form["phone"], delivery_address=form["delivery_address"], notes=form["notes"],
                pickup_event=form.get("pickup_event"),
            )
        except shop_services.ShopError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @extend_schema(summary="Cancelar encomenda (só se ainda não foi paga)", request=None,
                   responses={200: OrderSerializer, 400: DetailSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if not order.can_cancel:
            return Response({"detail": "Esta encomenda já foi paga — contacta o clube para alterações."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(shop_services.cancel_order(order, reason="cancelada pelo membro")).data)


# --- Premium -----------------------------------------------------------------------------
@extend_schema(tags=["Premium"], auth=[], summary="Planos premium", responses=PlanSerializer(many=True))
class PlanListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(PlanSerializer(Plan.objects.filter(is_active=True), many=True).data)


@extend_schema(tags=["Premium"])
class PremiumView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="O meu estado premium", responses=PremiumStatusSerializer)
    def get(self, request):
        subs = Subscription.objects.filter(user=request.user).select_related("plan")
        current = subs.active().order_by("-ends_at").first()
        pending = subs.pending().first()
        return Response(PremiumStatusSerializer({
            "is_premium": current is not None, "current": current, "pending": pending, "history": subs[:10],
        }).data)

    @extend_schema(summary="Pedir subscrição", request=SubscriptionCreateSerializer,
                   description="Cria um pedido pendente; o clube activa-o depois de confirmar o pagamento.",
                   responses={201: SubscriptionSerializer, 400: DetailSerializer})
    def post(self, request):
        serializer = SubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = get_object_or_404(Plan, slug=serializer.validated_data["plan"], is_active=True)
        try:
            sub = billing_services.request_subscription(request.user, plan)
        except billing_services.SubscriptionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SubscriptionSerializer(sub).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Premium"], summary="Cancelar pedido pendente", request=None,
               responses={204: None, 400: DetailSerializer})
class PremiumCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            billing_services.cancel_request(request.user, pk)
        except billing_services.SubscriptionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)
