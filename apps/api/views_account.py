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
from rest_framework.generics import DestroyAPIView
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import Device, User
from apps.core.emails import send_templated_email

from .serializers import (
    AuthResultSerializer,
    DetailSerializer,
    DeviceSerializer,
    MemberSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
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


@extend_schema(tags=["Notificações"], request=DeviceSerializer, responses={200: DeviceSerializer, 201: DeviceSerializer},
               summary="Registar dispositivo para notificações push",
               description="Idempotente: enviar o mesmo token de novo apenas actualiza o registo (e passa-o para o membro actual).")
class DeviceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = DeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        device, created = Device.objects.update_or_create(
            token=d["token"], defaults={"user": request.user, "platform": d["platform"],
                                        "app_version": d.get("app_version", "")})
        return Response(DeviceSerializer(device).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@extend_schema(tags=["Notificações"], summary="Remover dispositivo (ao terminar sessão)", responses={204: None})
class DeviceDeleteView(DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "token"
    lookup_url_kwarg = "token"

    def get_queryset(self):
        return Device.objects.filter(user=self.request.user) if not getattr(self, "swagger_fake_view", False) else Device.objects.none()
