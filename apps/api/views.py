"""API REST v1 — prepara o terreno para uma app móvel nativa (fase 3)."""
from datetime import timedelta

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts import ratelimit
from apps.activity import services as activity
from apps.activity.models import PointTransaction, Run
from apps.events import services as event_services
from apps.events import tickets
from apps.events.models import Event, Registration
from apps.leaderboard.services import get_leaderboard

from .authentication import token_is_expired
from .serializers import (
    DashboardSerializer,
    DetailSerializer,
    EventSerializer,
    LeaderboardSerializer,
    MemberSerializer,
    PointTransactionSerializer,
    RegisterRequestSerializer,
    RegistrationSerializer,
    RunSerializer,
    TokenRequestSerializer,
    TokenResponseSerializer,
)


@extend_schema(tags=["Autenticação"], auth=[], request=TokenRequestSerializer, responses={
    200: TokenResponseSerializer, 400: DetailSerializer, 429: DetailSerializer}, summary="Iniciar sessão (obter token)")
class TokenView(ObtainAuthToken):
    """POST {username: email, password} → {token, expires_in}. Mesmo rate-limit por email/IP que o login web."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
    authentication_classes = []  # um token caducado/revogado no cabeçalho não pode impedir um novo login

    def post(self, request, *args, **kwargs):
        email = str(request.data.get("username", ""))
        if ratelimit.is_blocked(request, email):
            return Response({"detail": "Demasiadas tentativas falhadas. Aguarda alguns minutos."},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        serializer = self.serializer_class(data=request.data, context={"request": request})
        if not serializer.is_valid():
            ratelimit.register_failure(request, email)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        ratelimit.reset(request, email)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        if token_is_expired(token):  # renova: apaga o token caducado e emite um novo
            token.delete()
            token = Token.objects.create(user=user)
        return Response({"token": token.key, "expires_in": settings.API_TOKEN_TTL_DAYS * 86400})


@extend_schema(tags=["Autenticação"], request=None, responses={204: None}, summary="Terminar sessão (revogar token)")
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def logout(request):
    """Revoga o token usado no pedido."""
    if request.auth is not None and hasattr(request.auth, "delete"):
        request.auth.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Perfil"], methods=["GET", "PATCH"], request=MemberSerializer, responses=MemberSerializer,
               summary="Ver ou editar o meu perfil")
@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def me(request):
    if request.method == "PATCH":
        serializer = MemberSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
    data = MemberSerializer(request.user, context={"request": request}).data
    return Response(data)


@extend_schema(tags=["Perfil"], responses=DashboardSerializer, summary="Estatísticas, semana e próximos eventos")
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def dashboard(request):
    stats = activity.member_stats(request.user)
    stats["total_time"] = int(stats["total_time"].total_seconds())
    week = [{"date": d["date"], "label": d["label"], "km": d["km"]} for d in activity.weekly_activity(request.user)]
    upcoming = Registration.objects.filter(
        user=request.user, status=Registration.Status.CONFIRMED, event__starts_at__gte=timezone.now()
    ).select_related("event").order_by("event__starts_at")[:5]
    return Response({
        "stats": stats,
        "week": week,
        "upcoming": RegistrationSerializer(upcoming, many=True).data,
    })


@extend_schema_view(
    list=extend_schema(summary="Listar eventos", parameters=[
        OpenApiParameter("when", str, enum=["past"], description="Omitir para eventos futuros; `past` para passados.")]),
    retrieve=extend_schema(summary="Detalhe de um evento"),
    register=extend_schema(
        summary="Inscrever-me", request=RegisterRequestSerializer, responses={201: RegistrationSerializer, 400: DetailSerializer},
        description="**Eventos da ETK:** cria o bilhete. Grátis ou M-Pesa: `status=confirmed` e `qr_value` na resposta. "
                    "Pago por e-Mola/mKesh/cartão: `status=pending` com `payment_instructions` — sondar `GET …/ticket/` "
                    "até `status=confirmed` (ou `checkout_url` para cartão). Pré-inscrição: `payment=preregistered`, "
                    "confirmar depois com `POST …/confirm/`. Exige telemóvel no perfil."),
    cancel=extend_schema(summary="Cancelar a minha inscrição", request=None,
                         description="Não disponível para bilhetes da ETK (a organização é quem cancela).",
                         responses={200: RegistrationSerializer, 400: DetailSerializer}),
    ticket=extend_schema(summary="O meu bilhete neste evento", responses=RegistrationSerializer),
    confirm=extend_schema(summary="Confirmar presença (pré-inscrição)", request=None,
                          responses={200: RegistrationSerializer, 400: DetailSerializer}),
)
@extend_schema(tags=["Eventos"])
class EventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSerializer
    lookup_field = "slug"
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = Event.objects.with_counts()
        return qs.past() if self.request.query_params.get("when") == "past" else qs.upcoming()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.request.user.is_authenticated:
            ctx["my_event_ids"] = set(Registration.objects.filter(
                user=self.request.user, status=Registration.Status.CONFIRMED).values_list("event_id", flat=True))
        return ctx

    def get_object(self):
        # Inclui eventos passados, para que register/cancel devolvam o erro de negócio certo
        event = get_object_or_404(Event.objects.published().with_counts(), slug=self.kwargs["slug"])
        self.check_object_permissions(self.request, event)
        return event

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def register(self, request, slug=None):
        event = self.get_object()
        body = RegisterRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        d = body.validated_data
        try:
            if event.is_external:
                reg = tickets.buy_ticket(request.user, event, d.get("price", ""), d.get("payment_method", ""))
            else:
                reg = event_services.register(request.user, event, d.get("distance", ""))
        except (event_services.RegistrationError, tickets.TicketError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RegistrationSerializer(reg).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def cancel(self, request, slug=None):
        event = self.get_object()
        try:
            reg = event_services.cancel(request.user, event)
        except event_services.RegistrationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RegistrationSerializer(reg).data)

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def ticket(self, request, slug=None):
        """O meu bilhete neste evento, com o estado actual do pagamento na ETK (para sondar enquanto está pendente)."""
        event = self.get_object()
        reg = get_object_or_404(Registration, event=event, user=request.user)
        return Response(RegistrationSerializer(tickets.refresh_registration(reg)).data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def confirm(self, request, slug=None):
        """Pré-inscrição: confirma a presença."""
        event = self.get_object()
        try:
            reg = tickets.confirm_presence(request.user, event)
        except tickets.TicketError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RegistrationSerializer(reg).data)


@extend_schema_view(
    list=extend_schema(summary="As minhas corridas"),
    create=extend_schema(summary="Registar corrida", description="Aplica as regras anti-batota (data, ritmo, limites diários)."),
    retrieve=extend_schema(summary="Detalhe de uma corrida"),
    destroy=extend_schema(summary="Apagar corrida (remove os pontos)"),
)
@extend_schema(tags=["Corridas e pontos"])
class RunViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                 mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = RunSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # geração do esquema OpenAPI
            return Run.objects.none()
        return Run.objects.filter(user=self.request.user).prefetch_related("point_transactions")

    def perform_create(self, serializer):
        d = serializer.validated_data
        serializer.instance = activity.log_run(
            self.request.user, date=d["date"], distance_km=d["distance_km"],
            duration=timedelta(seconds=d["duration_seconds"]), title=d.get("title", ""), notes=d.get("notes", ""),
        )

    def perform_destroy(self, instance):
        activity.delete_run(instance)


@extend_schema(tags=["Corridas e pontos"], summary="Os meus movimentos de pontos")
class PointViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PointTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PointTransaction.objects.none()
        return PointTransaction.objects.filter(user=self.request.user)


@extend_schema(
    tags=["Ranking"], auth=[], responses=LeaderboardSerializer, summary="Ranking (público)",
    parameters=[
        OpenApiParameter("period", str, enum=["mes", "geral"], default="mes", description="Período."),
        OpenApiParameter("metric", str, enum=["pontos", "km"], default="pontos", description="Métrica."),
    ],
)
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def leaderboard(request):
    period = request.query_params.get("period", "mes")
    metric = request.query_params.get("metric", "pontos")
    rows = get_leaderboard(period, metric)
    return Response({"period": period, "metric": metric, "results": rows})
