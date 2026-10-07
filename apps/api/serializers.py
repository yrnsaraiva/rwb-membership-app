from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import User
from apps.activity.forms import MAX_BACKDATE_DAYS
from apps.activity.models import PointTransaction, Run
from apps.activity.services import run_limit_error
from apps.events.models import Event, Registration


class MemberSerializer(serializers.ModelSerializer):
    is_premium = serializers.BooleanField(read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "member_number", "email", "first_name", "last_name", "phone", "city", "date_of_birth", "bio",
                  "show_on_leaderboard", "avatar_url", "is_premium", "date_joined"]
        read_only_fields = ["id", "member_number", "email", "date_joined"]

    @extend_schema_field(serializers.URLField(allow_null=True))
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
    cover_url = serializers.CharField(read_only=True)
    requires_ticket = serializers.BooleanField(source="has_paid_ticket", read_only=True,
                                               help_text="Bilhete pago: a inscrição faz-se no site de bilhetes (`external_url`).")
    tickets_available = serializers.IntegerField(read_only=True)
    ticket_prices = serializers.JSONField(read_only=True)

    class Meta:
        model = Event
        fields = ["id", "slug", "title", "kind", "kind_display", "summary", "description", "location", "meeting_point",
                  "map_url", "starts_at", "ends_at", "distances", "capacity", "spots_left", "confirmed_total",
                  "registration_opens_at", "registration_closes_at", "registration_is_open", "price_mzn",
                  "members_only", "is_registered", "cover_url", "requires_ticket", "tickets_available", "ticket_prices",
                  "external_url"]

    @extend_schema_field(serializers.BooleanField())
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
        user = self.context["request"].user
        error = run_limit_error(user, date=attrs["date"], distance_km=attrs["distance_km"],
                                duration=timedelta(seconds=attrs["duration_seconds"]))
        if error:
            raise serializers.ValidationError(error)
        return attrs


class PointTransactionSerializer(serializers.ModelSerializer):
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = PointTransaction
        fields = ["id", "amount", "reason", "reason_display", "description", "created_at"]


# --- Respostas sem modelo (só para a documentação OpenAPI) -------------------------------
class TokenRequestSerializer(serializers.Serializer):
    username = serializers.EmailField(help_text="Email do membro.")
    password = serializers.CharField(write_only=True)


class TokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    expires_in = serializers.IntegerField(help_text="Validade do token, em segundos.")


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


class StatsSerializer(serializers.Serializer):
    total_km = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_runs = serializers.IntegerField()
    total_time = serializers.IntegerField(help_text="Segundos.")
    total_time_display = serializers.CharField()
    month_km = serializers.DecimalField(max_digits=10, decimal_places=2)
    points = serializers.IntegerField()
    month_points = serializers.IntegerField()
    current_streak = serializers.IntegerField()
    longest_streak = serializers.IntegerField()
    ran_today = serializers.BooleanField()
    avg_pace = serializers.IntegerField(allow_null=True, help_text="Segundos por km.")
    avg_pace_display = serializers.CharField()


class WeekDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    label = serializers.CharField()
    km = serializers.DecimalField(max_digits=8, decimal_places=2)


class DashboardSerializer(serializers.Serializer):
    stats = StatsSerializer()
    week = WeekDaySerializer(many=True)
    upcoming = RegistrationSerializer(many=True)


class LeaderboardRowSerializer(serializers.Serializer):
    rank = serializers.IntegerField(help_text="Empates partilham o mesmo lugar.")
    user_id = serializers.IntegerField()
    name = serializers.CharField()
    initials = serializers.CharField()
    member_number = serializers.CharField()
    avatar_url = serializers.CharField(allow_blank=True)
    score = serializers.DecimalField(max_digits=12, decimal_places=2)


class LeaderboardSerializer(serializers.Serializer):
    period = serializers.CharField()
    metric = serializers.CharField()
    results = LeaderboardRowSerializer(many=True)


# --- Conta: registo, palavra-passe, dispositivos ------------------------------------------
class RegisterSerializer(serializers.Serializer):
    """Valida com o mesmo RegisterForm do site, para as regras nunca divergirem."""

    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    accept_terms = serializers.BooleanField(help_text="Tem de ser verdadeiro.")

    def validate(self, attrs):
        from apps.accounts.forms import RegisterForm

        form = RegisterForm({**attrs, "password1": attrs["password"], "password2": attrs["password"]})
        if not form.is_valid():
            errors = {("password" if k == "password1" else k): v for k, v in form.errors.items() if k != "password2"}
            raise serializers.ValidationError(errors)
        attrs["form"] = form
        return attrs


class AuthResultSerializer(serializers.Serializer):
    token = serializers.CharField()
    expires_in = serializers.IntegerField(help_text="Validade do token, em segundos.")
    member = MemberSerializer()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(help_text="`uidb64` do link enviado por email.")
    token = serializers.CharField(help_text="Token do link enviado por email.")
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})


class PushKeysSerializer(serializers.Serializer):
    p256dh = serializers.CharField(max_length=255)
    auth = serializers.CharField(max_length=255)


class PushSubscriptionSerializer(serializers.Serializer):
    """Formato de `PushSubscription.toJSON()` do navegador."""

    endpoint = serializers.URLField(max_length=700)
    keys = PushKeysSerializer()
    expirationTime = serializers.FloatField(required=False, allow_null=True, write_only=True)


class PushUnsubscribeSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=700)


class PushConfigSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    public_key = serializers.CharField(allow_blank=True)


# --- Staff: cartão QR e presenças -----------------------------------------------------------
class StaffRegistrationSerializer(serializers.ModelSerializer):
    event = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    event_title = serializers.CharField(source="event.title", read_only=True)
    starts_at = serializers.DateTimeField(source="event.starts_at", read_only=True)
    checkin_points = serializers.IntegerField(source="event.effective_checkin_points", read_only=True)

    class Meta:
        model = Registration
        fields = ["id", "event", "event_title", "starts_at", "status", "distance", "checked_in_at", "checkin_points"]


class StaffMemberCardSerializer(serializers.Serializer):
    member = MemberSerializer()
    is_active = serializers.BooleanField()
    registrations = StaffRegistrationSerializer(many=True, help_text="Inscrições confirmadas nas últimas/próximas 12 horas.")


# --- Loja --------------------------------------------------------------------------------
class VariantSerializer(serializers.ModelSerializer):
    price_mzn = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    unit_price_mzn = serializers.SerializerMethodField(help_text="Preço para o utilizador autenticado (com desconto premium).")

    class Meta:
        from apps.shop.models import ProductVariant

        model = ProductVariant
        fields = ["id", "name", "stock", "price_mzn", "unit_price_mzn"]

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_unit_price_mzn(self, obj):
        price = obj.unit_price_for(self.context["request"].user)
        return serializers.DecimalField(max_digits=10, decimal_places=2).to_representation(price)  # mesmo formato que os outros preços


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    premium_price_mzn = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    images = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        from apps.shop.models import Product

        model = Product
        fields = ["id", "slug", "name", "category", "category_name", "summary", "description", "price_mzn",
                  "premium_price_mzn", "compare_at_price_mzn", "size_guide", "is_featured", "in_stock", "images", "variants"]

    @extend_schema_field(serializers.ListField(child=serializers.URLField()))
    def get_images(self, obj):
        request = self.context["request"]
        return [request.build_absolute_uri(i.image.url) for i in obj.images.all()]

    @extend_schema_field(VariantSerializer(many=True))
    def get_variants(self, obj):
        active = [v for v in obj.variants.all() if v.is_active]
        return VariantSerializer(active, many=True, context=self.context).data


class ShopConfigSerializer(serializers.Serializer):
    delivery_fee_mzn = serializers.DecimalField(max_digits=10, decimal_places=2)
    premium_discount_percent = serializers.IntegerField()
    hold_days = serializers.IntegerField(help_text="Dias até a encomenda por pagar ser cancelada.")
    mpesa_number = serializers.CharField(allow_blank=True)
    mpesa_name = serializers.CharField(allow_blank=True)
    bank_details = serializers.CharField(allow_blank=True)
    pickup_events = EventSerializer(many=True, help_text="Eventos onde se pode levantar a encomenda.")


class OrderItemInputSerializer(serializers.Serializer):
    variant = serializers.IntegerField(help_text="ID da variante (tamanho).")
    quantity = serializers.IntegerField(min_value=1, max_value=10)


class OrderCreateSerializer(serializers.Serializer):
    items = OrderItemInputSerializer(many=True, allow_empty=False)
    fulfilment = serializers.ChoiceField(choices=["event", "pickup", "delivery"])
    pickup_event = serializers.IntegerField(required=False, allow_null=True, help_text="ID do evento (se fulfilment=event).")
    customer_name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=20)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate(self, attrs):
        from apps.shop.forms import CheckoutForm

        form = CheckoutForm({k: ("" if v is None else v) for k, v in attrs.items() if k != "items"})
        if not form.is_valid():
            raise serializers.ValidationError({k: v for k, v in form.errors.items()})
        attrs["form"] = form
        return attrs


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        from apps.shop.models import OrderItem

        model = OrderItem
        fields = ["product_name", "variant_name", "quantity", "unit_price_mzn", "list_price_mzn", "line_total"]


class OrderSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    fulfilment_display = serializers.CharField(source="get_fulfilment_display", read_only=True)
    pickup_event = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    can_cancel = serializers.BooleanField(read_only=True)

    class Meta:
        from apps.shop.models import Order

        model = Order
        fields = ["id", "number", "status", "status_display", "fulfilment", "fulfilment_display", "pickup_event",
                  "customer_name", "phone", "delivery_address", "notes", "subtotal_mzn", "discount_mzn",
                  "delivery_fee_mzn", "total_mzn", "payment_method", "payment_reference", "paid_at", "created_at",
                  "can_cancel", "items"]


# --- Premium -----------------------------------------------------------------------------
class PlanSerializer(serializers.ModelSerializer):
    benefits = serializers.ListField(child=serializers.CharField(), source="benefit_list", read_only=True)

    class Meta:
        from apps.billing.models import Plan

        model = Plan
        fields = ["id", "slug", "name", "price_mzn", "duration_days", "description", "benefits", "is_featured"]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    days_left = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        from apps.billing.models import Subscription

        model = Subscription
        fields = ["id", "plan", "plan_name", "status", "status_display", "amount_mzn", "starts_at", "ends_at",
                  "days_left", "created_at"]


class SubscriptionCreateSerializer(serializers.Serializer):
    plan = serializers.SlugField(help_text="`slug` do plano.")


class PremiumStatusSerializer(serializers.Serializer):
    is_premium = serializers.BooleanField()
    current = SubscriptionSerializer(allow_null=True)
    pending = SubscriptionSerializer(allow_null=True)
    history = SubscriptionSerializer(many=True)


class TicketScanSerializer(serializers.Serializer):
    qrValue = serializers.CharField(max_length=60, help_text="Conteúdo do QR do bilhete: `TCKT…|assinatura`.")


class TicketScanResultSerializer(serializers.Serializer):
    result = serializers.ChoiceField(choices=["ok", "already_entered", "not_paid", "not_found", "invalid_qr", "error"])
    message = serializers.CharField()
    holder = serializers.CharField(allow_blank=True)
    event = serializers.CharField(allow_blank=True)
    member = serializers.DictField(allow_null=True, help_text="`{name, member_number}` se o titular for membro.")
    points = serializers.IntegerField(help_text="Pontos atribuídos agora (0 se já tinha presença ou não é membro).")
    registered = serializers.BooleanField()
