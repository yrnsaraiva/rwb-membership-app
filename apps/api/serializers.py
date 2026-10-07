from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User
from apps.activity.forms import MAX_BACKDATE_DAYS
from apps.activity.models import PointTransaction, Run
from apps.events.models import Event, Registration


class MemberSerializer(serializers.ModelSerializer):
    is_premium = serializers.BooleanField(read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "member_number", "email", "first_name", "last_name", "phone", "city", "date_of_birth", "bio",
                  "show_on_leaderboard", "avatar_url", "is_premium", "date_joined"]
        read_only_fields = ["id", "member_number", "email", "date_joined"]

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url


class EventSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    spots_left = serializers.IntegerField(read_only=True)
    confirmed_total = serializers.IntegerField(read_only=True)
    registration_is_open = serializers.BooleanField(read_only=True)
    is_registered = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ["id", "slug", "title", "kind", "kind_display", "summary", "description", "location", "meeting_point",
                  "map_url", "starts_at", "ends_at", "distances", "capacity", "spots_left", "confirmed_total",
                  "registration_opens_at", "registration_closes_at", "registration_is_open", "price_mzn",
                  "members_only", "is_registered"]

    def get_is_registered(self, obj):
        ids = self.context.get("my_event_ids")
        return obj.pk in ids if ids is not None else False


class RegistrationSerializer(serializers.ModelSerializer):
    event = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = Registration
        fields = ["id", "event", "status", "distance", "checked_in_at", "created_at"]


class RunSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.IntegerField(write_only=True, min_value=1)
    duration = serializers.DurationField(read_only=True)
    pace_seconds = serializers.IntegerField(read_only=True)
    points = serializers.IntegerField(read_only=True)

    class Meta:
        model = Run
        fields = ["id", "date", "distance_km", "duration_seconds", "duration", "pace_seconds", "points", "title",
                  "notes", "is_valid", "created_at"]
        read_only_fields = ["id", "is_valid", "created_at"]

    def validate_date(self, value):
        t = timezone.localdate()
        if value > t:
            raise serializers.ValidationError("Não podes registar corridas no futuro.")
        if value < t - timedelta(days=MAX_BACKDATE_DAYS):
            raise serializers.ValidationError(f"Só é possível registar corridas dos últimos {MAX_BACKDATE_DAYS} dias.")
        return value

    def validate_distance_km(self, value):
        if value < Decimal("0.1") or value > settings.RWB_MAX_RUN_KM:
            raise serializers.ValidationError(f"Distância deve estar entre 0,1 e {settings.RWB_MAX_RUN_KM} km.")
        return value

    def validate(self, attrs):
        pace = attrs["duration_seconds"] / float(attrs["distance_km"])
        if pace < settings.RWB_MIN_PACE_SEC_PER_KM:
            raise serializers.ValidationError("Ritmo demasiado rápido para ser real.")
        return attrs


class PointTransactionSerializer(serializers.ModelSerializer):
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = PointTransaction
        fields = ["id", "amount", "reason", "reason_display", "description", "created_at"]
