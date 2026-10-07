from django.contrib import admin, messages
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from . import services
from .models import Category, Order, OrderItem, Product, ProductImage, ProductVariant


def pending_orders_badge(request):
    """Contador no menu lateral do Unfold."""
    n = Order.objects.filter(status=Order.Status.PENDING).count()
    return n or None


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ["name", "slug", "order"]
    list_editable = ["order"]
    prepopulated_fields = {"slug": ["name"]}


class VariantInline(TabularInline):
    model = ProductVariant
    extra = 1
    fields = ["name", "sku", "stock", "price_override_mzn", "is_active", "order"]
    tab = True


class ImageInline(StackedInline):
    model = ProductImage
    extra = 1
    fields = ["image", "alt", "order"]
    tab = True


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ["thumb", "name", "category", "price_mzn", "stock_display", "is_active", "is_featured"]
    list_display_links = ["thumb", "name"]
    list_filter = ["is_active", "is_featured", "category"]
    list_editable = ["is_active", "is_featured"]
    search_fields = ["name", "variants__sku"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [VariantInline, ImageInline]
    fieldsets = (
        (None, {"fields": ("name", "slug", "category", "summary", "description", "size_guide")}),
        ("Preço e visibilidade", {"fields": ("price_mzn", "compare_at_price_mzn", "is_active", "is_featured", "order")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("variants", "images")

    @admin.display(description="")
    def thumb(self, obj):
        img = obj.main_image
        if not img:
            return "—"
        return format_html('<img src="{}" style="width:40px;height:40px;object-fit:cover;border-radius:8px">', img.image.url)

    @admin.display(description="Stock")
    def stock_display(self, obj):
        return obj.total_stock


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ["product_name", "variant_name", "quantity", "unit_price_mzn", "list_price_mzn"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.action(description="Marcar como pagas (M-Pesa manual)")
def mark_paid(modeladmin, request, queryset):
    done = 0
    for order in queryset:
        try:
            services.mark_paid(order)
            done += 1
        except services.ShopError:
            pass
    messages.success(request, f"{done} encomenda(s) marcada(s) como paga(s).")


@admin.action(description="Marcar como prontas para entrega")
def mark_ready(modeladmin, request, queryset):
    done = 0
    for order in queryset:
        try:
            services.advance(order, Order.Status.READY)
            done += 1
        except services.ShopError:
            pass
    messages.success(request, f"{done} encomenda(s) pronta(s).")


@admin.action(description="Marcar como entregues")
def mark_completed(modeladmin, request, queryset):
    done = 0
    for order in queryset:
        try:
            services.advance(order, Order.Status.COMPLETED)
            done += 1
        except services.ShopError:
            pass
    messages.success(request, f"{done} encomenda(s) entregue(s).")


@admin.action(description="Cancelar e devolver stock")
def cancel_orders(modeladmin, request, queryset):
    done = 0
    for order in queryset:
        try:
            services.cancel_order(order, reason=f"cancelada por {request.user.email}")
            done += 1
        except services.ShopError:
            pass
    messages.success(request, f"{done} encomenda(s) cancelada(s).")


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ["number", "customer_name", "phone", "status", "fulfilment", "total_mzn", "created_at"]
    list_filter = ["status", "fulfilment", "payment_method"]
    search_fields = ["id", "customer_name", "phone", "user__email", "user__member_number", "payment_reference"]
    readonly_fields = ["user", "subtotal_mzn", "discount_mzn", "delivery_fee_mzn", "total_mzn", "paid_at",
                       "completed_at", "cancelled_at", "created_at", "updated_at"]
    inlines = [OrderItemInline]
    actions = [mark_paid, mark_ready, mark_completed, cancel_orders]
    fieldsets = (
        (None, {"fields": ("user", "status", "customer_name", "phone")}),
        ("Entrega", {"fields": ("fulfilment", "pickup_event", "delivery_address", "notes")}),
        ("Valores", {"fields": ("subtotal_mzn", "discount_mzn", "delivery_fee_mzn", "total_mzn")}),
        ("Pagamento", {"fields": ("payment_method", "payment_reference", "paid_at")}),
        ("Histórico", {"fields": ("completed_at", "cancelled_at", "created_at", "updated_at", "staff_notes")}),
    )

    @admin.display(description="Nº", ordering="id")
    def number(self, obj):
        return obj.number
