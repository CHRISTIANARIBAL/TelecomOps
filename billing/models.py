
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from django.conf import settings

class Customer(models.Model):

    class CustomerType(models.TextChoices):
        RESIDENTIAL = "RESIDENTIAL", "Residential"
        SME = "SME", "Small and Medium Enterprise"
        CORPORATE = "CORPORATE", "Corporate"

    customer_id = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    customer_type = models.CharField(
        max_length=20,
        choices=CustomerType.choices,
        default=CustomerType.RESIDENTIAL,
    )

    # Individual customer information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    # Business customer information
    company_name = models.CharField(max_length=200, blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    tin = models.CharField(max_length=50, blank=True)

    # Contact information
    contact_number = models.CharField(max_length=20)
    email = models.EmailField(blank=True)

    # Address information
    address = models.TextField()
    city = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)

        if not self.customer_id:
            self.customer_id = f"CUS-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(
                customer_id=self.customer_id
            )
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.customer_id} - {self.company_name or f'{self.first_name} {self.last_name}'}"


class InternetPlan(models.Model):

    class ServiceType(models.TextChoices):
        RESIDENTIAL = "RESIDENTIAL", "Residential"
        SME = "SME", "SME"
        DIA = "DIA", "DIA (Dedicated Internet Access)"

    plan_name = models.CharField(max_length=150, unique=True)

    service_type = models.CharField(
        max_length=20,
        choices=ServiceType.choices,
        default=ServiceType.RESIDENTIAL,
    )

    description = models.TextField(blank=True)

    download_speed = models.PositiveIntegerField(
        help_text="Download speed in Mbps"
    )

    upload_speed = models.PositiveIntegerField(
        help_text="Upload speed in Mbps"
    )
    burst_download_speed = models.PositiveIntegerField(
    default=0,
    validators=[MinValueValidator(0)],
    help_text="Maximum burst download speed in Mbps. 0 means no burst."
    )

    burst_upload_speed = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Maximum burst upload speed in Mbps. 0 means no burst."
    )

    monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["monthly_price"]

    def __str__(self):
        return f"{self.plan_name} - ₱{self.monthly_price:,.2f}"


class Subscription(models.Model):

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        DISCONNECTED = "DISCONNECTED", "Disconnected"
        CANCELLED = "CANCELLED", "Cancelled"

    subscription_number = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    internet_plan = models.ForeignKey(
        InternetPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    pppoe_username = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
    )

    installation_date = models.DateField()

    # Manually assigned billing day: 1 to 31
    billing_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)

        if not self.subscription_number:
            self.subscription_number = f"SUB-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(
                subscription_number=self.subscription_number
            )
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subscription_number} - {self.customer}"



class Invoice(models.Model):

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        UNPAID = "UNPAID", "Unpaid"
        PARTIALLY_PAID = "PARTIALLY_PAID", "Partially Paid"
        PAID = "PAID", "Paid"
        OVERDUE = "OVERDUE", "Overdue"
        VOID = "VOID", "Void"

    invoice_number = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="invoices",
    )

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        related_name="invoices",
    )

    billing_period_start = models.DateField()
    billing_period_end = models.DateField()
    issue_date = models.DateField()
    due_date = models.DateField()

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "subscription",
                    "billing_period_start",
                    "billing_period_end",
                ],
                name="unique_subscription_billing_period",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)

        if not self.invoice_number:
            self.invoice_number = f"INV-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(
                invoice_number=self.invoice_number
            )
        else:
            super().save(*args, **kwargs)

    @property
    def amount_paid(self):
        return sum(
            (allocation.amount for allocation in self.payment_allocations.filter(
                payment__status=Payment.Status.COMPLETED
            )),
            Decimal("0.00"),
        )

    @property
    def balance(self):
        return self.total_amount - self.amount_paid

    def __str__(self):
        return f"{self.invoice_number} - {self.customer}"


class InvoiceItem(models.Model):

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="items",
    )

    description = models.CharField(max_length=255)

    quantity = models.PositiveIntegerField(default=1)

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return self.description


class Payment(models.Model):

    class PaymentMethod(models.TextChoices):
        CASH = "CASH", "Cash"
        GCASH = "GCASH", "GCash"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        REVERSED = "REVERSED", "Reversed"

    payment_number = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="payments",
    )

    payment_date = models.DateField()

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
    )

    reference_number = models.CharField(
        max_length=100,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.COMPLETED,
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)

        if not self.payment_number:
            self.payment_number = f"PAY-{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(
                payment_number=self.payment_number
            )
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.payment_number} - ₱{self.amount:,.2f}"


class PaymentAllocation(models.Model):

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="allocations",
    )

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payment_allocations",
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.payment.payment_number} → {self.invoice.invoice_number}"


class BillingActivity(models.Model):

    class ActionType(models.TextChoices):
        CUSTOMER_CREATED = "CUSTOMER_CREATED", "Customer Created"
        CUSTOMER_UPDATED = "CUSTOMER_UPDATED", "Customer Updated"

        PLAN_CREATED = "PLAN_CREATED", "Internet Plan Created"
        PLAN_UPDATED = "PLAN_UPDATED", "Internet Plan Updated"

        SUBSCRIPTION_CREATED = "SUBSCRIPTION_CREATED", "Subscription Created"
        SUBSCRIPTION_UPDATED = "SUBSCRIPTION_UPDATED", "Subscription Updated"
        SUBSCRIPTION_SUSPENDED = "SUBSCRIPTION_SUSPENDED", "Subscription Suspended"
        SUBSCRIPTION_REACTIVATED = "SUBSCRIPTION_REACTIVATED", "Subscription Reactivated"

        INVOICE_CREATED = "INVOICE_CREATED", "Invoice Created"
        INVOICE_UPDATED = "INVOICE_UPDATED", "Invoice Updated"
        INVOICE_VOIDED = "INVOICE_VOIDED", "Invoice Voided"

        PAYMENT_RECORDED = "PAYMENT_RECORDED", "Payment Recorded"
        PAYMENT_REVERSED = "PAYMENT_REVERSED", "Payment Reversed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_activities",
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_activities",
    )

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_activities",
    )

    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_activities",
    )

    action = models.CharField(
        max_length=40,
        choices=ActionType.choices,
    )

    description = models.TextField()

    details = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Billing Activity"
        verbose_name_plural = "Billing Activities"

    def __str__(self):
        return f"{self.get_action_display()} - {self.created_at:%Y-%m-%d %H:%M}"
