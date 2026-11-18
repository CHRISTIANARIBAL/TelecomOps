from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.conf import settings
from billing.models import Customer
from inventory.models import Product

class Sale(models.Model):

    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Completed"
        VOID = "VOID", "Voided"

    sale_number = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    # Optional registered customer
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales",
    )

    # Preserve the buyer's name at the time of sale
    buyer_name = models.CharField(max_length=200)

    # Employee who processed the transaction
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="processed_sales",
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="released_sales",
    )

    sale_date = models.DateTimeField(auto_now_add=True)

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.COMPLETED,
    )

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-sale_date", "-id"]

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)

        if not self.sale_number:
            self.sale_number = f"SALE-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(
                sale_number=self.sale_number
            )
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return self.sale_number or f"Sale #{self.pk}"


class SaleItem(models.Model):

    sale = models.ForeignKey(
        Sale,
        on_delete=models.PROTECT,
        related_name="items",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="sale_items",
    )

    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class SaleEditHistory(models.Model):
    sale = models.ForeignKey(
        Sale,
        on_delete=models.PROTECT,
        related_name="edit_history",
    )

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sale_edits",
    )

    edited_at = models.DateTimeField(auto_now_add=True)

    description = models.TextField()

    class Meta:
        ordering = ["-edited_at", "-id"]
        verbose_name = "Sale Edit History"
        verbose_name_plural = "Sale Edit Histories"

    def __str__(self):
        return f"{self.sale.sale_number} edited on {self.edited_at}"
