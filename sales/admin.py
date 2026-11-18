from django.contrib import admin
from .models import Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ("amount",)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "sale_number",
        "buyer_name",
        "customer",
        "processed_by",
        "sale_date",
        "total_amount",
        "status",
    )

    search_fields = (
        "sale_number",
        "buyer_name",
        "customer__first_name",
        "customer__last_name",
        "customer__company_name",
    )

    list_filter = (
        "status",
        "sale_date",
    )

    readonly_fields = (
        "sale_number",
        "sale_date",
    )

    inlines = [SaleItemInline]


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = (
        "sale",
        "product",
        "quantity",
        "unit_price",
        "amount",
    )

    search_fields = (
        "sale__sale_number",
        "product__sku",
        "product__name",
    )