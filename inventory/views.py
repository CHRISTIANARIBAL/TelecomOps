
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, F, Count, Q, Value, IntegerField
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from .models import Category, Product, StockBalance, ProductImage, StockAdjustment
from .forms import ProductForm, ProductUpdateForm, CategoryForm
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.urls import reverse

def dashboard(request):

    # Product statistics
    total_products = Product.objects.filter(
        is_active=True
    ).count()

    # Category statistics
    total_categories = Category.objects.filter(
        is_active=True
    ).count()

    # Total stock quantity
    total_stock = StockBalance.objects.filter(
        product__is_active=True
    ).aggregate(
        total=Sum("quantity_on_hand")
    )["total"] or 0

    # Total inventory value based on cost price
    total_inventory_value = StockBalance.objects.filter(
        product__is_active=True
    ).aggregate(
        total=Sum(
            F("quantity_on_hand") * F("product__cost_price")
        )
    )["total"] or 0

    # Low stock products
    low_stock_products = Product.objects.filter(
        is_active=True,
        stock_balance__quantity_on_hand__lte=F("minimum_stock")
    ).select_related(
        "category",
        "stock_balance"
    ).order_by(
        "stock_balance__quantity_on_hand"
    )

    # Products grouped by category
    category_statistics = Category.objects.filter(
        is_active=True
    ).annotate(
        total_products=Count(
            "products",
            filter=F("products__is_active")
        )
    ).order_by("name")

    # Recently added products
    recent_products = Product.objects.filter(
        is_active=True
    ).select_related(
        "category"
    ).order_by("-created_at")[:5]

    context = {
        "total_products": total_products,
        "total_categories": total_categories,
        "total_stock": total_stock,
        "total_inventory_value": total_inventory_value,
        "low_stock_count": low_stock_products.count(),
        "low_stock_products": low_stock_products[:5],
        "category_statistics": category_statistics,
        "recent_products": recent_products,
        "active_page": "inventory",
    }

    return render(
        request,
        "inventory/dashboard.html",
        context
    )

def products(request):

    search_query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()
    selected_status = request.GET.get("status", "active").strip()

    # Product statistics
    total_products = Product.objects.count()

    active_products = Product.objects.filter(
        is_active=True,
        category__is_active=True,
    ).filter(
        Q(category__parent__isnull=True) |
        Q(category__parent__is_active=True)
    ).count()

    inactive_products = Product.objects.filter(
        is_active=False
    ).count()

    unavailable_products = Product.objects.filter(
        is_active=True
    ).filter(
        Q(category__is_active=False) |
        Q(category__parent__is_active=False)
    ).count()
    # Start with all products
    product_list = Product.objects.select_related(
        "category"
    ).annotate(
        current_stock=Coalesce(
            "stock_balance__quantity_on_hand",
            Value(0),
            output_field=IntegerField()
        ),
        sold_quantity=Coalesce(
            Sum(
                "sale_items__quantity",
                filter=Q(sale_items__sale__status="COMPLETED")
            ),
            Value(0),
            output_field=IntegerField()
        )
    )

    # Filter by status
    if selected_status == "active":
        product_list = product_list.filter(
            is_active=True,
            category__is_active=True,
        ).filter(
            Q(category__parent__isnull=True) |
            Q(category__parent__is_active=True)
        )

    elif selected_status == "inactive":
        product_list = product_list.filter(is_active=False)

    # Search products
    if search_query:
        product_list = product_list.filter(
            Q(sku__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Filter by category
    if category_id:
        product_list = product_list.filter(
            category_id=category_id
        )

    product_list = product_list.order_by("name", "id")

    # Pagination
    paginator = Paginator(product_list, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "products": page_obj,
        "page_obj": page_obj,
        "categories": Category.objects.filter(is_active=True, parent__isnull=True).order_by("name"),
        "search_query": search_query,
        "selected_category": category_id,
        "selected_status": selected_status,
        "total_products": total_products,
        "active_products": active_products,
        "inactive_products": inactive_products,
        "unavailable_products": unavailable_products,
        "active_page": "inventory_products",
    }

    return render(
        request,
        "inventory/products.html",
        context
    )


def add_product(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    product = form.save(commit=False)
                    new_category_name = form.cleaned_data.get(
                        "new_category_name"
                    )
                    new_subcategory_name = form.cleaned_data.get(
                        "new_subcategory_name"
                    )
                    # Create a new main category if requested.
                    if new_category_name:
                        category = Category.objects.create(
                            name=new_category_name,
                            description=form.cleaned_data.get(
                                "new_category_description", ""
                            )
                        )

                        product.category = category

                    # Create a new subcategory under the selected main category.
                    if new_subcategory_name:
                        subcategory = Category.objects.create(
                            name=new_subcategory_name,
                            parent=product.category
                        )

                        product.subcategory = subcategory

                    # Save product.
                    product.save()

                    # Save multiple product images.
                    uploaded_images = request.FILES.getlist("images")

                    for index, image in enumerate(uploaded_images):
                        ProductImage.objects.create(
                            product=product,
                            image=image,
                            is_primary=(index == 0)
                        )

                    # Create initial stock balance
                    StockBalance.objects.create(
                        product=product,
                        quantity_on_hand=form.cleaned_data[
                            "initial_stock"
                        ]
                    )

                messages.success(
                    request,
                    f"Product {product.name} was successfully added."
                )

                return redirect("inventory:products")

            except Exception as e:
                messages.error(
                    request,
                    "Unable to save product. Please check the information and try again."
                )

        else:
            messages.error(
                request,
                "Please correct the errors in the form."
            )

    else:
        form = ProductForm()

    context = {
        "form": form,
        "categories": Category.objects.filter(
            is_active=True,
            parent__isnull=True
        ),
        "subcategories": list(
            Category.objects.filter(
                is_active=True,
                parent__isnull=False
            ).values("id", "name", "parent_id")
        ),
        "active_page": "inventory_products",
    }

    return render(
        request,
        "inventory/add_product.html",
        context
    )


def product_detail(request, pk):

    product = get_object_or_404(
        Product.objects.select_related(
            "category",
            "stock_balance"
        ),
        pk=pk
    )

    # Safely retrieve stock information
    stock_balance = getattr(product, "stock_balance", None)

    quantity_on_hand = (
        stock_balance.quantity_on_hand
        if stock_balance else 0
    )

    quantity_reserved = (
        stock_balance.quantity_reserved
        if stock_balance else 0
    )

    available_stock = (
        stock_balance.available_stock
        if stock_balance else 0
    )

    context = {
        "product": product,
        "quantity_on_hand": quantity_on_hand,
        "quantity_reserved": quantity_reserved,
        "available_stock": available_stock,
        "active_page": "inventory_products",
    }

    return render(
        request,
        "inventory/product_detail.html",
        context
    )


def edit_product(request, pk):

    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        form = ProductUpdateForm(
            request.POST,
            request.FILES,
            instance=product
        )

        if form.is_valid():
            try:
                with transaction.atomic():

                    updated_product = form.save(commit=False)

                    new_category_name = form.cleaned_data.get(
                        "new_category_name"
                    )

                    new_subcategory_name = form.cleaned_data.get(
                        "new_subcategory_name"
                    )

                    # Create a new main category if requested.
                    if new_category_name:
                        category = Category.objects.create(
                            name=new_category_name,
                            description=form.cleaned_data.get(
                                "new_category_description", ""
                            )
                        )

                        updated_product.category = category
                        updated_product.subcategory = None

                    # Create a new subcategory under the selected main category.
                    if new_subcategory_name:
                        subcategory = Category.objects.create(
                            name=new_subcategory_name,
                            parent=updated_product.category
                        )

                        updated_product.subcategory = subcategory

                    updated_product.save()

                    # ==========================================
                    # STOCK ADJUSTMENT
                    # ==========================================

                    new_stock_quantity = form.cleaned_data.get(
                        "new_stock_quantity"
                    )

                    adjustment_reason = form.cleaned_data.get(
                        "stock_adjustment_reason", ""
                    ).strip()

                    if new_stock_quantity is not None:

                        if updated_product.tracking_type != Product.TrackingType.QUANTITY:
                            raise ValidationError(
                                "Manual quantity adjustment is only available for quantity-based products."
                            )

                        if not adjustment_reason:
                            raise ValidationError(
                                "Please provide a reason for the stock adjustment."
                            )

                        # Retrieve and lock the existing stock balance.
                        stock_balance, _ = StockBalance.objects.get_or_create(
                            product=updated_product
                        )

                        stock_balance = StockBalance.objects.select_for_update().get(
                            pk=stock_balance.pk
                        )

                        previous_quantity = stock_balance.quantity_on_hand

                        # Prevent stock from going below reserved quantity.
                        if new_stock_quantity < stock_balance.quantity_reserved:
                            raise ValidationError(
                                f"New stock cannot be lower than reserved stock "
                                f"({stock_balance.quantity_reserved})."
                            )

                        quantity_change = new_stock_quantity - previous_quantity

                        # Only record an adjustment when the quantity actually changes.
                        if quantity_change != 0:

                            stock_balance.quantity_on_hand = new_stock_quantity

                            stock_balance.save(
                                update_fields=["quantity_on_hand", "updated_at"]
                            )

                            StockAdjustment.objects.create(
                                product=updated_product,
                                adjusted_by=request.user,
                                previous_quantity=previous_quantity,
                                new_quantity=new_stock_quantity,
                                quantity_change=quantity_change,
                                reason=adjustment_reason,
                            )

                    # Save additional product gallery images.
                    uploaded_images = request.FILES.getlist("images")

                    for image in uploaded_images:
                        ProductImage.objects.create(
                            product=updated_product,
                            image=image,
                            is_primary=not updated_product.images.filter(
                                is_primary=True
                            ).exists()
                        )

                messages.success(
                    request,
                    f"{updated_product.name} was successfully updated."
                )

                return redirect("inventory:products")

            except ValidationError as error:
                for message in error.messages:
                    form.add_error(None, message)

            except IntegrityError:
                messages.error(
                    request,
                    "Unable to update the product. The SKU or category may already exist."
                )

        else:
            messages.error(
                request,
                "Please correct the errors in the form."
            )

    else:
        form = ProductUpdateForm(instance=product)

    context = {
        "form": form,
        "product": product,
        "categories": Category.objects.filter(
            Q(is_active=True, parent__isnull=True) |
            Q(pk=product.category_id)
        ),
        "subcategories": list(
            Category.objects.filter(
                Q(is_active=True, parent__isnull=False) |
                Q(pk=product.subcategory_id)
            ).values("id", "name", "parent_id")
        ),
        "active_page": "inventory_products",
    }

    return render(
        request,
        "inventory/edit_product.html",
        context
    )


@require_POST
def toggle_product_status(request, pk):

    product = get_object_or_404(Product, pk=pk)

    product.is_active = not product.is_active
    product.save(update_fields=["is_active", "updated_at"])

    if product.is_active:
        messages.success(
            request,
            f"{product.name} has been activated."
        )
        return redirect(
            f"{reverse('inventory:products')}?status=active"
        )

    messages.success(
        request,
        f"{product.name} has been deactivated."
    )

    return redirect(
        f"{reverse('inventory:products')}?status=inactive"
    )



# ==========================================
# CATEGORY MANAGEMENT
# ==========================================

def categories(request):

    search_query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "active").strip()

    # Category statistics
    total_categories = Category.objects.count()
    active_categories = Category.objects.filter(is_active=True).count()
    inactive_categories = Category.objects.filter(is_active=False).count()

    # Start with all categories
    category_list = Category.objects.select_related(
        "parent"
    ).annotate(
        total_products=(
            Count("products", distinct=True) +
            Count("subcategorized_products", distinct=True)
        ),
        active_products_count=(
            Count(
                "products",
                filter=Q(products__is_active=True),
                distinct=True
            ) +
            Count(
                "subcategorized_products",
                filter=Q(subcategorized_products__is_active=True),
                distinct=True
            )
        )
    )

    # Filter by status
    if selected_status == "active":
        category_list = category_list.filter(is_active=True)

    elif selected_status == "inactive":
        category_list = category_list.filter(is_active=False)

    # Search categories
    if search_query:
        category_list = category_list.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    category_list = category_list.order_by("name")

    # Pagination
    paginator = Paginator(category_list, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "categories": page_obj,
        "page_obj": page_obj,
        "search_query": search_query,
        "selected_status": selected_status,
        "total_categories": total_categories,
        "active_categories": active_categories,
        "inactive_categories": inactive_categories,
        "active_page": "inventory_categories",
    }

    return render(
        request,
        "inventory/categories.html",
        context
    )


def add_category(request):

    if request.method == "POST":
        form = CategoryForm(request.POST)

        if form.is_valid():
            category = form.save()

            messages.success(
                request,
                f"Category '{category.name}' was successfully added."
            )

            return redirect("inventory:categories")

        messages.error(
            request,
            "Please correct the errors in the form."
        )

    else:
        form = CategoryForm()

    context = {
        "form": form,
        "active_page": "inventory_categories",
    }

    return render(
        request,
        "inventory/add_category.html",
        context
    )


def edit_category(request, pk):

    category = get_object_or_404(Category, pk=pk)

    if request.method == "POST":
        form = CategoryForm(
            request.POST,
            instance=category
        )

        if form.is_valid():
            updated_category = form.save()

            messages.success(
                request,
                f"Category '{updated_category.name}' was successfully updated."
            )

            return redirect("inventory:categories")

        messages.error(
            request,
            "Please correct the errors in the form."
        )

    else:
        form = CategoryForm(instance=category)

    context = {
        "form": form,
        "category": category,
        "active_page": "inventory_categories",
    }

    return render(
        request,
        "inventory/edit_category.html",
        context
    )


@require_POST
def toggle_category_status(request, pk):

    category = get_object_or_404(Category, pk=pk)

    category.is_active = not category.is_active

    category.save(
        update_fields=["is_active", "updated_at"]
    )

    if category.is_active:
        messages.success(
            request,
            f"Category '{category.name}' has been activated."
        )

        return redirect(
            f"{reverse('inventory:categories')}?status=active"
        )

    messages.success(
        request,
        f"Category '{category.name}' has been deactivated."
    )

    return redirect(
        f"{reverse('inventory:categories')}?status=inactive"
    )
