
from django.db import models
from django.db.models import Sum


class Category(models.Model):

    name = models.CharField(max_length=150, unique=True)

    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subcategories",
    )

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} → {self.name}"

        return self.name

    @property
    def product_count(self):
        return self.products.filter(is_active=True).count()

    @property
    def is_subcategory(self):
        return self.parent_id is not None


class Product(models.Model):

    class TrackingType(models.TextChoices):
        QUANTITY = "QUANTITY", "Quantity Based"
        SERIALIZED = "SERIALIZED", "Serialized"

    sku = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Product SKU"
    )

    name = models.CharField(max_length=200)
    image = models.ImageField(
        upload_to="products/",
        blank=True,
        null=True,
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products"
    )

    subcategory = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subcategorized_products"
    )

    tracking_type = models.CharField(
        max_length=20,
        choices=TrackingType.choices,
        default=TrackingType.QUANTITY
    )

    description = models.TextField(blank=True)

    unit_of_measure = models.CharField(
        max_length=30,
        default="pcs",
        verbose_name="Unit of Measure"
    )

    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    minimum_stock = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["subcategory"]),
        ]

    def __str__(self):
        return f"{self.sku} - {self.name}"

    @property
    def total_stock(self):
        return self.stock_balance.quantity_on_hand if hasattr(
            self, "stock_balance"
        ) else 0


class StockBalance(models.Model):

    product = models.OneToOneField(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_balance"
    )

    quantity_on_hand = models.PositiveIntegerField(default=0)

    quantity_reserved = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["product__name"]

    def __str__(self):
        return f"{self.product.name} - {self.quantity_on_hand}"

    @property
    def available_stock(self):
        return self.quantity_on_hand - self.quantity_reserved

class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images"
    )

    image = models.ImageField(
        upload_to="products/gallery/"
    )

    is_primary = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "created_at"]

    def __str__(self):
        return f"{self.product.name} - Image {self.pk}"