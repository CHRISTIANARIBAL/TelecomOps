
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model

from inventory.models import Product
from .forms import SaleForm, SaleEditForm
from .services import create_sale, update_sale
from .models import Sale

User = get_user_model()

@login_required
def sell_product(request, product_id):

    product = get_object_or_404(
        Product.objects.select_related(
            "category",
            "category__parent",
            "stock_balance",
        ),
        pk=product_id,
    )

    if not product.is_active:
        messages.error(request, "This product is inactive.")
        return redirect("inventory:product_detail", pk=product.pk)

    if not product.category.is_active:
        messages.error(
            request,
            "This product belongs to an inactive category."
        )
        return redirect("inventory:product_detail", pk=product.pk)

    if product.category.parent_id and not product.category.parent.is_active:
        messages.error(
            request,
            "This product belongs to an inactive parent category."
        )
        return redirect("inventory:product_detail", pk=product.pk)

    if request.method == "POST":
        form = SaleForm(request.POST)

        if form.is_valid():
            try:
                sale = create_sale(
                    product_id=product.pk,
                    quantity=form.cleaned_data["quantity"],
                    unit_price=form.cleaned_data["unit_price"],
                    buyer_name=form.cleaned_data["buyer_name"],
                    customer=form.cleaned_data["customer"],
                    processed_by=request.user,
                    released_by=form.cleaned_data["released_by"],
                    notes=form.cleaned_data["notes"],
                )

                messages.success(
                    request,
                    f"Sale {sale.sale_number} completed successfully."
                )

                return redirect(
                    "inventory:product_detail",
                    pk=product.pk,
                )

            except ValidationError as error:
                for message in error.messages:
                    form.add_error(None, message)

    else:
        form = SaleForm(
            initial={
                "quantity": 1,
                "unit_price": (
                    product.selling_price
                    if product.selling_price is not None
                    else Decimal("0.00")
                ),
            }
        )

    return render(
        request,
        "sales/sell_product.html",
        {
            "form": form,
            "product": product,
            "active_page": "sales",
        },
    )


@login_required
def sales_list(request):
    search_query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    selected_employee = request.GET.get("employee", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    # Start with all sales
    sales = (
        Sale.objects
        .select_related("customer", "processed_by", "released_by")
        .prefetch_related("items__product")
        .order_by("-sale_date", "-id")
    )

    # Search transaction number, buyer, product, SKU, and employees
    if search_query:
        sales = sales.filter(
            Q(sale_number__icontains=search_query) |
            Q(buyer_name__icontains=search_query) |
            Q(items__product__name__icontains=search_query) |
            Q(items__product__sku__icontains=search_query) |
            Q(processed_by__username__icontains=search_query) |
            Q(released_by__username__icontains=search_query) |
            Q(released_by__first_name__icontains=search_query) |
            Q(released_by__last_name__icontains=search_query)
        ).distinct()

    # Filter by transaction status
    valid_statuses = [choice[0] for choice in Sale.Status.choices]

    if selected_status in valid_statuses:
        sales = sales.filter(status=selected_status)

    # Filter by releasing employee
    if selected_employee.isdigit():
        sales = sales.filter(released_by_id=int(selected_employee))

    # Filter by date range
    if date_from:
        sales = sales.filter(sale_date__date__gte=date_from)

    if date_to:
        sales = sales.filter(sale_date__date__lte=date_to)

    # Pagination: 25 transactions per page
    paginator = Paginator(sales, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    employees = User.objects.filter(
        role=User.Role.EMPLOYEE,
        is_active=True,
        is_approved=True,
        email_verified=True,
        approval_status=User.ApprovalStatus.APPROVED,
    ).order_by("first_name", "last_name", "username")

    context = {
        "sales": page_obj,
        "page_obj": page_obj,
        "total_records": paginator.count,
        "employees": employees,
        "search_query": search_query,
        "selected_status": selected_status,
        "selected_employee": selected_employee,
        "date_from": date_from,
        "date_to": date_to,
        "active_page": "sales",
    }

    return render(request, "sales/sales_list.html", context)

@login_required
def sale_detail(request, pk):
    sale = get_object_or_404(
        Sale.objects
        .select_related("customer", "processed_by", "released_by")
        .prefetch_related("items__product"),
        pk=pk,
    )

    context = {
        "sale": sale,
        "active_page": "sales",
    }

    return render(request, "sales/sale_detail.html", context)


@login_required
def edit_sale(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related("customer", "processed_by", "released_by")
        .prefetch_related("items__product"),
        pk=pk,
    )

    if sale.status != Sale.Status.COMPLETED:
        messages.error(request, "Only completed transactions can be edited.")
        return redirect("sales:sale_detail", pk=sale.pk)

    items = list(sale.items.all())

    if len(items) != 1:
        messages.error(
            request,
            "This transaction cannot be edited because it does not contain exactly one product.",
        )
        return redirect("sales:sale_detail", pk=sale.pk)

    item = items[0]

    if request.method == "POST":
        form = SaleEditForm(request.POST)

        if form.is_valid():
            try:
                sale = update_sale(
                    sale_id=sale.pk,
                    quantity=form.cleaned_data["quantity"],
                    unit_price=form.cleaned_data["unit_price"],
                    buyer_name=form.cleaned_data["buyer_name"],
                    customer=form.cleaned_data["customer"],
                    notes=form.cleaned_data["notes"],
                    edited_by=request.user,
                )

                messages.success(
                    request,
                    f"Transaction {sale.sale_number} updated successfully.",
                )

                return redirect("sales:sale_detail", pk=sale.pk)

            except ValidationError as error:
                for message in error.messages:
                    form.add_error(None, message)

    else:
        form = SaleEditForm(
            initial={
                "customer": sale.customer,
                "buyer_name": sale.buyer_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "notes": sale.notes,
            }
        )

    return render(
        request,
        "sales/edit_sale.html",
        {
            "form": form,
            "sale": sale,
            "item": item,
            "product": item.product,
            "active_page": "sales",
        },
    )
