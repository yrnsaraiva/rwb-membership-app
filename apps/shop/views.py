from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from . import services
from .cart import MAX_QTY_PER_LINE, Cart
from .forms import CheckoutForm
from .models import Category, Order, Product, ProductVariant


def product_list(request):
    categories = Category.objects.filter(products__is_active=True).distinct()
    cat = request.GET.get("categoria", "")
    products = Product.objects.active().select_related("category").prefetch_related("images", "variants")
    if cat:
        products = products.filter(category__slug=cat)
    return render(request, "shop/list.html", {
        "products": products, "categories": categories, "current_category": cat,
        "premium_discount": settings.RWB_PREMIUM_SHOP_DISCOUNT,
    })


def product_detail(request, slug):
    product = get_object_or_404(Product.objects.active().prefetch_related("images", "variants"), slug=slug)
    variants = [v for v in product.variants.all() if v.is_active]
    default = next((v for v in variants if v.stock > 0), None)
    related = Product.objects.active().exclude(pk=product.pk).prefetch_related("images")
    if product.category_id:
        related = related.filter(category_id=product.category_id)
    return render(request, "shop/detail.html", {
        "product": product, "variants": variants, "default_variant": default,
        "related": related[:4], "max_qty": MAX_QTY_PER_LINE, "delivery_fee": settings.RWB_SHOP_DELIVERY_FEE,
        "premium_discount": settings.RWB_PREMIUM_SHOP_DISCOUNT,
    })


@require_POST
def cart_add(request, slug):
    product = get_object_or_404(Product.objects.active(), slug=slug)
    try:
        variant = product.variants.get(pk=int(request.POST.get("variant", 0)), is_active=True)
        qty = max(1, min(int(request.POST.get("quantity", 1)), MAX_QTY_PER_LINE))
    except (ProductVariant.DoesNotExist, ValueError, TypeError):
        messages.error(request, "Escolhe uma opção válida.")
        return redirect(product.get_absolute_url())
    cart = Cart(request)
    if cart.quantity_of(variant.pk) + qty > variant.stock:
        messages.error(request, f"Stock insuficiente para {variant.name} (disponível: {variant.stock}).")
        return redirect(product.get_absolute_url())
    cart.add(variant.pk, qty)
    messages.success(request, f"{product.name} ({variant.name}) adicionado ao carrinho.")
    if request.POST.get("next") == "checkout":
        return redirect("shop:checkout")
    return redirect("shop:cart")


@require_http_methods(["GET", "POST"])
def cart_view(request):
    cart = Cart(request)
    if request.method == "POST":
        for key, value in request.POST.items():
            if key.startswith("qty_"):
                try:
                    cart.set(int(key[4:]), int(value))
                except ValueError:
                    pass
        if "remove" in request.POST:
            cart.remove(request.POST["remove"])
        return redirect("shop:cart")
    return render(request, "shop/cart.html", {"summary": cart.summary(), "max_qty": MAX_QTY_PER_LINE})


@login_required
@require_http_methods(["GET", "POST"])
def checkout(request):
    cart = Cart(request)
    if not cart.count:
        messages.info(request, "O teu carrinho está vazio.")
        return redirect("shop:list")
    form = CheckoutForm(request.POST or None, user=request.user)
    fulfilment = request.POST.get("fulfilment") or form.initial.get("fulfilment") or form.fields["fulfilment"].initial
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            order = services.place_order(
                request.user, cart, fulfilment=d["fulfilment"], customer_name=d["customer_name"], phone=d["phone"],
                delivery_address=d["delivery_address"], notes=d["notes"], pickup_event=d.get("pickup_event"),
            )
        except services.ShopError as exc:
            messages.error(request, str(exc))
            return redirect("shop:cart")
        messages.success(request, f"Encomenda {order.number} registada! Segue as instruções de pagamento.")
        return redirect(order.get_absolute_url())
    return render(request, "shop/checkout.html", {
        "form": form, "summary": cart.summary(fulfilment), "delivery_fee": settings.RWB_SHOP_DELIVERY_FEE,
    })


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    return render(request, "shop/orders.html", {"orders": orders})


@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items").select_related("pickup_event"), pk=pk, user=request.user)
    return render(request, "shop/order_detail.html", {"order": order, "payment": services.payment_instructions()})


@login_required
@require_POST
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if not order.can_cancel:
        messages.error(request, "Esta encomenda já foi paga — contacta o clube para alterações.")
    else:
        services.cancel_order(order, reason="cancelada pelo membro")
        messages.info(request, f"Encomenda {order.number} cancelada.")
    return redirect(order.get_absolute_url())
