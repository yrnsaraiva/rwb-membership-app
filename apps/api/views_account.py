"""Conta: registo, recuperação/mudança de palavra-passe e dispositivos push."""
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.emails import send_templated_email
from apps.notifications import services as push_services
from apps.notifications.models import PushSubscription

from .serializers import (
    AuthResultSerializer,
    DetailSerializer,
    MemberSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PushConfigSerializer,
    PushSubscriptionSerializer,
    PushUnsubscribeSerializer,
    RegisterSerializer,
    TokenResponseSerializer,
)


def _auth_payload(user, request):
    token, _ = Token.objects.get_or_create(user=user)
    return {"token": token.key, "expires_in": settings.API_TOKEN_TTL_DAYS * 86400,
            "member": MemberSerializer(user, context={"request": request}).data}


@extend_schema(tags=["Autenticação"], auth=[], request=RegisterSerializer, summary="Criar conta de membro",
               responses={201: AuthResultSerializer, 400: DetailSerializer})
class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["form"].save()
        send_templated_email("welcome", user.email, {"user": user})
        return Response(_auth_payload(user, request), status=status.HTTP_201_CREATED)


@extend_schema(tags=["Autenticação"], auth=[], request=PasswordResetRequestSerializer, responses={204: None},
               summary="Pedir recuperação de palavra-passe",
               description="Envia um email com o link de recuperação. Responde sempre 204, exista ou não a conta.")
class PasswordResetView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        form = PasswordResetForm({"email": serializer.validated_data["email"]})
        if form.is_valid():
            form.save(request=request, email_template_name="emails/password_reset.txt",
                      html_email_template_name="emails/password_reset.html",
                      subject_template_name="emails/password_reset_subject.txt")
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Autenticação"], auth=[], request=PasswordResetConfirmSerializer, summary="Definir nova palavra-passe",
               description="Usa o `uid` e o `token` do link do email de recuperação. Revoga os tokens da API existentes.",
               responses={204: None, 400: DetailSerializer})
class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(d["uid"])))
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, d["token"]):
            return Response({"detail": "Link inválido ou expirado."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            password_validation.validate_password(d["password"], user)
        except DjangoValidationError as exc:
            return Response({"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(d["password"])
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Perfil"], request=PasswordChangeSerializer, summary="Mudar a palavra-passe",
               description="Revoga os tokens existentes e devolve um novo, para o dispositivo actual continuar com sessão.",
               responses={200: TokenResponseSerializer, 400: DetailSerializer})
class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        if not request.user.check_password(d["old_password"]):
            return Response({"old_password": ["Palavra-passe actual incorrecta."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            password_validation.validate_password(d["new_password"], request.user)
        except DjangoValidationError as exc:
            return Response({"new_password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(d["new_password"])
        request.user.save()
        payload = _auth_payload(request.user, request)
        return Response({"token": payload["token"], "expires_in": payload["expires_in"]})


@extend_schema(tags=["Notificações"], auth=[], responses=PushConfigSerializer, summary="Configuração Web Push",
               description="`public_key` é a chave VAPID (base64url) para `pushManager.subscribe({applicationServerKey})`.")
class PushConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"enabled": push_services.is_enabled(), "public_key": settings.VAPID_PUBLIC_KEY})


@extend_schema(tags=["Notificações"])
class PushSubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(summary="Guardar subscrição Web Push deste navegador", request=PushSubscriptionSerializer,
                   description="Idempotente. Enviar o objecto devolvido por `PushSubscription.toJSON()`.",
                   responses={200: PushUnsubscribeSerializer, 201: PushUnsubscribeSerializer})
    def post(self, request):
        serializer = PushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        sub, created = PushSubscription.objects.update_or_create(
            endpoint=d["endpoint"],
            defaults={"user": request.user, "p256dh": d["keys"]["p256dh"], "auth": d["keys"]["auth"], "failures": 0,
                      "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255]})
        return Response({"endpoint": sub.endpoint}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(summary="Remover subscrição Web Push", request=PushUnsubscribeSerializer, responses={204: None})
    def delete(self, request):
        serializer = PushUnsubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PushSubscription.objects.filter(user=request.user, endpoint=serializer.validated_data["endpoint"]).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
