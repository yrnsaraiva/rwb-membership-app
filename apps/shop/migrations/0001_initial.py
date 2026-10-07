import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.shop.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("events", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60, verbose_name="nome")),
                ("slug", models.SlugField(blank=True, unique=True)),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="ordem")),
            ],
            options={"verbose_name": "categoria", "verbose_name_plural": "categorias", "ordering": ["order", "name"]},
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, verbose_name="nome")),
                ("slug", models.SlugField(blank=True, max_length=140, unique=True)),
                ("summary", models.CharField(blank=True, max_length=160, verbose_name="resumo")),
                ("description", models.TextField(blank=True, verbose_name="descrição")),
                ("price_mzn", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="preço (MZN)")),
                ("compare_at_price_mzn", models.DecimalField(blank=True, decimal_places=2, help_text="Mostrado riscado, para promoções.", max_digits=10, null=True, verbose_name="preço anterior (MZN)")),
                ("size_guide", models.TextField(blank=True, verbose_name="guia de tamanhos")),
                ("is_active", models.BooleanField(default=True, verbose_name="à venda")),
                ("is_featured", models.BooleanField(default=False, verbose_name="destaque")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="ordem")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="products", to="shop.category", verbose_name="categoria")),
            ],
            options={"verbose_name": "produto", "verbose_name_plural": "produtos", "ordering": ["order", "-created_at"]},
        ),
        migrations.CreateModel(
            name="ProductImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to=apps.shop.models.product_image_upload_to, verbose_name="imagem")),
                ("alt", models.CharField(blank=True, max_length=120, verbose_name="texto alternativo")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="ordem")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="shop.product", verbose_name="produto")),
            ],
            options={"verbose_name": "imagem", "verbose_name_plural": "imagens", "ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="ProductVariant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Ex.: S, M, L, XL ou Preto / M", max_length=40, verbose_name="opção")),
                ("sku", models.CharField(blank=True, max_length=40, verbose_name="SKU")),
                ("stock", models.PositiveIntegerField(default=0, verbose_name="stock")),
                ("price_override_mzn", models.DecimalField(blank=True, decimal_places=2, help_text="Vazio = preço do produto", max_digits=10, null=True, verbose_name="preço específico (MZN)")),
                ("is_active", models.BooleanField(default=True, verbose_name="activa")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="ordem")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="variants", to="shop.product", verbose_name="produto")),
            ],
            options={"verbose_name": "variante", "verbose_name_plural": "variantes", "ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "A aguardar pagamento"), ("paid", "Pago — em preparação"), ("ready", "Pronto para entrega"), ("completed", "Entregue"), ("cancelled", "Cancelada")], db_index=True, default="pending", max_length=12, verbose_name="estado")),
                ("fulfilment", models.CharField(choices=[("event", "Levantar num evento do clube"), ("pickup", "Levantar no ponto do clube"), ("delivery", "Entrega ao domicílio (Maputo/Matola)")], default="event", max_length=10, verbose_name="entrega")),
                ("customer_name", models.CharField(max_length=120, verbose_name="nome")),
                ("phone", models.CharField(max_length=20, verbose_name="telemóvel")),
                ("delivery_address", models.TextField(blank=True, verbose_name="morada de entrega")),
                ("notes", models.TextField(blank=True, max_length=500, verbose_name="notas do cliente")),
                ("subtotal_mzn", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="subtotal")),
                ("discount_mzn", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="desconto premium")),
                ("delivery_fee_mzn", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="taxa de entrega")),
                ("total_mzn", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="total")),
                ("payment_method", models.CharField(blank=True, choices=[("mpesa_manual", "M-Pesa (confirmação manual)"), ("cash", "Numerário"), ("bank", "Transferência bancária"), ("other", "Outro")], max_length=20, verbose_name="método de pagamento")),
                ("payment_reference", models.CharField(blank=True, max_length=80, verbose_name="referência do pagamento")),
                ("paid_at", models.DateTimeField(blank=True, null=True, verbose_name="pago em")),
                ("completed_at", models.DateTimeField(blank=True, null=True, verbose_name="entregue em")),
                ("cancelled_at", models.DateTimeField(blank=True, null=True, verbose_name="cancelada em")),
                ("staff_notes", models.TextField(blank=True, verbose_name="notas internas")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criada em")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("pickup_event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shop_orders", to="events.event", verbose_name="evento de levantamento")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="orders", to=settings.AUTH_USER_MODEL, verbose_name="membro")),
            ],
            options={"verbose_name": "encomenda", "verbose_name_plural": "encomendas", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product_name", models.CharField(max_length=120, verbose_name="produto")),
                ("variant_name", models.CharField(max_length=40, verbose_name="opção")),
                ("unit_price_mzn", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="preço unitário")),
                ("list_price_mzn", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="preço de tabela")),
                ("quantity", models.PositiveIntegerField(verbose_name="quantidade")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="shop.order", verbose_name="encomenda")),
                ("variant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="order_items", to="shop.productvariant", verbose_name="variante")),
            ],
            options={"verbose_name": "artigo", "verbose_name_plural": "artigos"},
        ),
    ]
