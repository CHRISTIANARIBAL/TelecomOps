
from django.contrib import admin
from .models import Category, Product, StockBalance


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "product_count",
        "is_active",
        "created_at",
    )

    search_fields = ("name",)
    list_filter = ("is_active",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "name",
        "category",
        "tracking_type",
        "cost_price",
        "selling_price",
        "minimum_stock",
        "total_stock",
        "is_active",
    )

    search_fields = ("sku", "name")
    list_filter = (
        "category",
        "tracking_type",
        "is_active",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "total_stock",
    )

    list_select_related = ("category",)


@admin.register(StockBalance)
class StockBalanceAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "quantity_on_hand",
        "quantity_reserved",
        "available_stock",
        "updated_at",
    )

    search_fields = (
        "product__sku",
        "product__name",
    )

    list_select_related = ("product",)

    readonly_fields = ("available_stock", "updated_at")
