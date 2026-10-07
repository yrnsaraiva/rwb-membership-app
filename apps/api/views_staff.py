"""Endpoints para o staff (check-in por QR nos eventos)."""
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.events import services as event_services
from apps.events import ticket_checkin
from apps.events.models import Registration

from .serializers import (
    DetailSerializer,
    MemberSerializer,
    StaffMemberCardSerializer,
    StaffRegistrationSerializer,
    TicketScanResultSerializer,
    TicketScanSerializer,
)


class IsStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff and request.user.is_active)


@extend_schema(tags=["Staff"], responses={200: StaffMemberCardSerializer, 404: DetailSerializer},
               summary="Ler cartão de membro (QR)",
               description="`token` é o UUID do QR (o último segmento do link `/conta/verificar/<token>/`). "
                           "Devolve o membro e as inscrições confirmadas nas últimas/próximas 12 horas.")
class MemberCardView(APIView):
    permission_classes = [IsStaff]

    def get(self, request, token):
        member = get_object_or_404(User, card_token=token)
        now = timezone.now()
        regs = Registration.objects.filter(
            user=member, status=Registration.Status.CONFIRMED,
            event__starts_at__gte=now - timedelta(hours=12), event__starts_at__lte=now + timedelta(hours=12),
        ).select_related("event")
        return Response({
            "member": MemberSerializer(member, context={"request": request}).data,
            "is_active": member.is_active,
            "registrations": StaffRegistrationSerializer(regs, many=True).data,
        })


@extend_schema(tags=["Staff"], summary="Marcar presença", request=None,
               responses={200: StaffRegistrationSerializer, 400: DetailSerializer})
class CheckInView(APIView):
    """POST marca presença (atribui pontos); DELETE desfaz."""

    permission_classes = [IsStaff]

    def _registration(self, pk):
        return get_object_or_404(Registration.objects.select_related("event", "user"), pk=pk)

    def post(self, request, pk):
        reg = self._registration(pk)
        if not event_services.check_in(reg):
            return Response({"detail": "Presença já registada ou inscrição cancelada."}, status=status.HTTP_400_BAD_REQUEST)
        reg.refresh_from_db()
        return Response(StaffRegistrationSerializer(reg).data)

    @extend_schema(summary="Desfazer presença", request=None, responses={200: StaffRegistrationSerializer})
    def delete(self, request, pk):
        reg = self._registration(pk)
        event_services.undo_check_in(reg)
        reg.refresh_from_db()
        return Response(StaffRegistrationSerializer(reg).data)


@extend_schema(tags=["Staff"], summary="Dar entrada com bilhete da ETK", request=TicketScanSerializer,
               description="Valida o bilhete na ETK (marca a entrada lá) e, se o titular for membro (pelo telemóvel/email do bilhete), "
                           "regista a presença e os pontos no RWB. `result`: ok, already_entered, not_paid, not_found, invalid_qr, error.",
               responses=TicketScanResultSerializer)
class TicketCheckInView(APIView):
    permission_classes = [IsStaff]

    def post(self, request):
        serializer = TicketScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(ticket_checkin.check_in_by_qr(serializer.validated_data["qrValue"]).as_dict())
