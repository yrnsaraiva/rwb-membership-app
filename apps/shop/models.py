"""
Loja de merch do clube.

Fase actual: SEM pagamento online. O membro faz a encomenda (o stock fica reservado), paga ao clube
por M-Pesa/transferência/numerário indicando o nº da encomenda, e o staff marca-a como paga no painel.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

RESERVED_SLUGS = {"carrinho", "checkout", "encomendas"}


def unique_slug(instance, value, max_length=140):
    base = slugify(value)[:max_length] or "item"
    if base in RESERVED_SLUGS:
        base = f"{base}-rwb"
    slug, n = base, 2
    model = type(instance)
    while model.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def premium_price(price: Decimal) -> Decimal:
    pct = Decimal(settings.RWB_PREMIUM_SHOP_DISCOUNT)
    if not pct:
        return price
    return (price * (Decimal(100) - pct) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class Category(models.Model):
    name = models.CharField("nome", max_length=60)
    slug = models.SlugField(unique=True, blank=True)
    order = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Product(models.Model):
    name = models.CharField("nome", max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="products", verbose_name="categoria")
    summary = models.CharField("resumo", max_length=160, blank=True)
    description = models.TextField("descrição", blank=True)
    price_mzn = models.DecimalField("preço (MZN)", max_digits=10, decimal_places=2)
    compare_at_price_mzn = models.DecimalField("preço anterior (MZN)", max_digits=10, decimal_places=2,
                                               null=True, blank=True, help_text="Mostrado riscado, para promoções.")
    size_guide = models.TextField("guia de tamanhos", blank=True)
    is_active = models.BooleanField("à venda", default=True)
    is_featured = models.BooleanField("destaque", default=False)
    order = models.PositiveSmallIntegerField("ordem", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("shop:product", args=[self.slug])

    @property
    def main_image(self):
        images = list(self.images.all())
        return images[0] if images else None

    @property
    def premium_price_mzn(self):
        return premium_price(self.price_mzn)

    @property
    def total_stock(self):
        return sum(v.stock for v in self.variants.all() if v.is_active)

    @property
    def in_stock(self):
        return self.total_stock > 0


def product_image_upload_to(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"shop/{instance.product.slug}-{instance.order}-{instance.product_id}.{ext}"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images", verbose_name="produto")
    image = models.ImageField("imagem", upload_to=product_image_upload_to)
    alt = models.CharField("texto alternativo", max_length=120, blank=True)
    order = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "imagem"
        verbose_name_plural = "imagens"
        ordering = ["order", "id"]

    def __str__(self):
        return self.alt or f"Imagem de {self.product}"


class ProductVariant(models.Model):
    """Tamanho/cor. Produtos sem opções têm uma única variante (ex.: 'Tamanho único')."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants", verbose_name="produto")
    name = models.CharField("opção", max_length=40, help_text="Ex.: S, M, L, XL ou Preto / M")
    sku = models.CharField("SKU", max_length=40, blank=True)
    stock = models.PositiveIntegerField("stock", default=0)
    price_override_mzn = models.DecimalField("preço específico (MZN)", max_digits=10, decimal_places=2,
                                             null=True, blank=True, help_text="Vazio = preço do produto")
    is_active = models.BooleanField("activa", default=True)
    order = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "variante"
        verbose_name_plural = "variantes"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.product.name} — {self.name}"

    @property
    def price_mzn(self):
        return self.price_override_mzn if self.price_override_mzn is not None else self.product.price_mzn

    def unit_price_for(self, user):
        if user is not None and getattr(user, "is_authenticated", False) and user.is_premium:
            return premium_price(self.price_mzn)
        return self.price_mzn


class OrderQuerySet(models.QuerySet):
    def open(self):
        return self.exclude(status__in=[Order.Status.COMPLETED, Order.Status.CANCELLED])


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "A aguardar pagamento"
        PAID = "paid", "Pago — em preparação"
        READY = "ready", "Pronto para entrega"
        COMPLETED = "completed", "Entregue"
        CANCELLED = "cancelled", "Cancelada"

    class Fulfilment(models.TextChoices):
        EVENT = "event", "Levantar num evento do clube"
        PICKUP = "pickup", "Levantar no ponto do clube"
        DELIVERY = "delivery", "Entrega ao domicílio (Maputo/Matola)"

    class Method(models.TextChoices):
        MPESA_MANUAL = "mpesa_manual", "M-Pesa (confirmação manual)"
        CASH = "cash", "Numerário"
        BANK = "bank", "Transferência bancária"
        OTHER = "other", "Outro"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders", verbose_name="membro")
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    fulfilment = models.CharField("entrega", max_length=10, choices=Fulfilment.choices, default=Fulfilment.EVENT)
    pickup_event = models.ForeignKey("events.Event", on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="shop_orders", verbose_name="evento de levantamento")
    customer_name = models.CharField("nome", max_length=120)
    phone = models.CharField("telemóvel", max_length=20)
    delivery_address = models.TextField("morada de entrega", blank=True)
    notes = models.TextField("notas do cliente", blank=True, max_length=500)
    subtotal_mzn = models.DecimalField("subtotal", max_digits=10, decimal_places=2, default=0)
    discount_mzn = models.DecimalField("desconto premium", max_digits=10, decimal_places=2, default=0)
    delivery_fee_mzn = models.DecimalField("taxa de entrega", max_digits=10, decimal_places=2, default=0)
    total_mzn = models.DecimalField("total", max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField("método de pagamento", max_length=20, choices=Method.choices, blank=True)
    payment_reference = models.CharField("referência do pagamento", max_length=80, blank=True)
    paid_at = models.DateTimeField("pago em", null=True, blank=True)
    completed_at = models.DateTimeField("entregue em", null=True, blank=True)
    cancelled_at = models.DateTimeField("cancelada em", null=True, blank=True)
    staff_notes = models.TextField("notas internas", blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        verbose_name = "encomenda"
        verbose_name_plural = "encomendas"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Encomenda {self.number}"

    @property
    def number(self):
        return f"L{self.pk:05d}" if self.pk else "—"

    def get_absolute_url(self):
        return reverse("shop:order", args=[self.pk])

    @property
    def can_cancel(self):
        return self.status == self.Status.PENDING

    @property
    def item_count(self):
        return sum(i.quantity for i in self.items.all())

    STEPS = [Status.PENDING, Status.PAID, Status.READY, Status.COMPLETED]

    def progress(self):
        """Lista de passos para a linha temporal da encomenda."""
        if self.status == self.Status.CANCELLED:
            return []
        current = self.STEPS.index(self.status)
        return [{"label": s.label, "done": i < current or self.status == self.Status.COMPLETED, "current": i == current
                 and self.status != self.Status.COMPLETED} for i, s in enumerate(self.STEPS)]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items", verbose_name="encomenda")
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="order_items", verbose_name="variante")
    product_name = models.CharField("produto", max_length=120)
    variant_name = models.CharField("opção", max_length=40)
    unit_price_mzn = models.DecimalField("preço unitário", max_digits=10, decimal_places=2)
    list_price_mzn = models.DecimalField("preço de tabela", max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField("quantidade")

    class Meta:
        verbose_name = "artigo"
        verbose_name_plural = "artigos"

    def __str__(self):
        return f"{self.quantity}× {self.product_name} ({self.variant_name})"

    @property
    def line_total(self):
        return self.unit_price_mzn * self.quantity
