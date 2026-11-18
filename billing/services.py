
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import (
    Subscription,
    Invoice,
    InvoiceItem,
    Payment,
    PaymentAllocation,
    BillingActivity,
)


def money(value, field_name):
    """Convert a value into a valid Decimal amount."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({
            field_name: "Enter a valid monetary amount."
        })

    if not amount.is_finite() or amount < 0:
        raise ValidationError({
            field_name: "Amount cannot be negative or invalid."
        })

    return amount.quantize(Decimal("0.01"))


@transaction.atomic
def generate_invoice(
    subscription_id,
    billing_period_start,
    billing_period_end,
    issue_date,
    due_date,
    discount=Decimal("0.00"),
    tax_amount=Decimal("0.00"),
    additional_items=None,
    notes="",
    performed_by=None,
):
    """
    Generate an invoice manually for a customer subscription.

    The monthly internet plan price is automatically included.
    Additional charges, discounts, and tax can also be supplied.
    """

    try:
        subscription = Subscription.objects.select_related(
            "customer",
            "internet_plan",
        ).get(pk=subscription_id)
    except Subscription.DoesNotExist:
        raise ValidationError("Subscription does not exist.")

    # Validate billing dates
    if billing_period_end < billing_period_start:
        raise ValidationError(
            "Billing period end cannot be before its start."
        )

    if due_date < issue_date:
        raise ValidationError(
            "Due date cannot be before the invoice issue date."
        )

    # Check for an existing invoice
    if Invoice.objects.filter(
        subscription=subscription,
        billing_period_start=billing_period_start,
        billing_period_end=billing_period_end,
    ).exists():
        raise ValidationError(
            "An invoice already exists for this subscription "
            "and billing period."
        )

    discount = money(discount, "discount")
    tax_amount = money(tax_amount, "tax_amount")

    # Prepare invoice items
    items = [
        {
            "description": (
                f"Internet Subscription - "
                f"{subscription.internet_plan.plan_name}"
            ),
            "quantity": 1,
            "unit_price": money(
                subscription.internet_plan.monthly_price,
                "monthly_price",
            ),
        }
    ]

    for item in additional_items or []:
        description = str(item.get("description", "")).strip()

        if not description:
            raise ValidationError(
                "Every additional item must have a description."
            )

        try:
            quantity = int(item.get("quantity", 1))
        except (TypeError, ValueError):
            raise ValidationError(
                "Additional item quantity must be a whole number."
            )

        if quantity < 1:
            raise ValidationError(
                "Additional item quantity must be at least 1."
            )

        unit_price = money(
            item.get("unit_price", 0),
            "unit_price",
        )

        items.append({
            "description": description,
            "quantity": quantity,
            "unit_price": unit_price,
        })

    # Calculate subtotal
    subtotal = sum(
        (
            item["quantity"] * item["unit_price"]
            for item in items
        ),
        Decimal("0.00"),
    )

    if discount > subtotal:
        raise ValidationError(
            "Discount cannot exceed the invoice subtotal."
        )

    total_amount = subtotal - discount + tax_amount

    try:
        with transaction.atomic():

            invoice = Invoice.objects.create(
                customer=subscription.customer,
                subscription=subscription,
                billing_period_start=billing_period_start,
                billing_period_end=billing_period_end,
                issue_date=issue_date,
                due_date=due_date,
                subtotal=subtotal,
                discount=discount,
                tax_amount=tax_amount,
                total_amount=total_amount,
                status=Invoice.Status.UNPAID,
                notes=notes,
            )

            # Create invoice line items
            InvoiceItem.objects.bulk_create([
                InvoiceItem(
                    invoice=invoice,
                    description=item["description"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    amount=item["quantity"] * item["unit_price"],
                )
                for item in items
            ])

            # Automatically record invoice activity
            BillingActivity.objects.create(
                user=performed_by,
                customer=subscription.customer,
                invoice=invoice,
                action=BillingActivity.ActionType.INVOICE_CREATED,
                description=(
                    f"Invoice {invoice.invoice_number} was generated."
                ),
                details={
                    "invoice_number": invoice.invoice_number,
                    "total_amount": str(invoice.total_amount),
                    "billing_period_start": str(billing_period_start),
                    "billing_period_end": str(billing_period_end),
                    "due_date": str(due_date),
                },
            )

            return invoice

    except IntegrityError:
        raise ValidationError(
            "An invoice already exists for this subscription "
            "and billing period."
        )


@transaction.atomic
def record_payment(
    customer_id,
    payment_date,
    amount,
    payment_method,
    allocations,
    reference_number="",
    notes="",
    performed_by=None,
):
    """Record a customer payment and allocate it to invoices."""

    amount = money(amount, "amount")

    if amount <= 0:
        raise ValidationError(
            "Payment amount must be greater than zero."
        )

    valid_methods = {
        choice[0] for choice in Payment.PaymentMethod.choices
    }

    if payment_method not in valid_methods:
        raise ValidationError("Invalid payment method.")

    if not allocations:
        raise ValidationError(
            "At least one invoice allocation is required."
        )

    prepared_allocations = []
    allocated_total = Decimal("0.00")

    for item in allocations:
        try:
            invoice_id = int(item["invoice_id"])
        except (KeyError, TypeError, ValueError):
            raise ValidationError("Invalid invoice ID.")

        allocation_amount = money(
            item.get("amount"),
            "allocation_amount",
        )

        if allocation_amount <= 0:
            raise ValidationError(
                "Allocation must be greater than zero."
            )

        prepared_allocations.append({
            "invoice_id": invoice_id,
            "amount": allocation_amount,
        })

        allocated_total += allocation_amount

    if allocated_total > amount:
        raise ValidationError(
            "Allocations cannot exceed the payment amount."
        )

    invoice_ids = [
        item["invoice_id"] for item in prepared_allocations
    ]

    if len(set(invoice_ids)) != len(invoice_ids):
        raise ValidationError(
            "An invoice cannot appear twice in one payment."
        )

    invoices = list(
        Invoice.objects.select_for_update()
        .filter(pk__in=sorted(invoice_ids))
        .order_by("pk")
    )

    invoice_map = {invoice.pk: invoice for invoice in invoices}

    if len(invoice_map) != len(set(invoice_ids)):
        raise ValidationError("One or more invoices do not exist.")

    for item in prepared_allocations:
        invoice = invoice_map[item["invoice_id"]]

        if invoice.customer_id != customer_id:
            raise ValidationError(
                "Invoice does not belong to the selected customer."
            )

        if invoice.status in (
            Invoice.Status.DRAFT,
            Invoice.Status.VOID,
        ):
            raise ValidationError(
                f"Invoice {invoice.invoice_number} cannot receive payments."
            )

        if item["amount"] > invoice.balance:
            raise ValidationError(
                f"Allocation exceeds the balance of "
                f"{invoice.invoice_number}."
            )

    payment = Payment.objects.create(
        customer_id=customer_id,
        payment_date=payment_date,
        amount=amount,
        payment_method=payment_method,
        reference_number=reference_number,
        status=Payment.Status.COMPLETED,
        notes=notes,
    )

    for item in prepared_allocations:
        PaymentAllocation.objects.create(
            payment=payment,
            invoice=invoice_map[item["invoice_id"]],
            amount=item["amount"],
        )

    today = timezone.localdate()

    for invoice in invoices:
        invoice.refresh_from_db()

        if invoice.balance <= 0:
            invoice.status = Invoice.Status.PAID
        elif invoice.amount_paid > 0:
            invoice.status = Invoice.Status.PARTIALLY_PAID
        elif invoice.due_date < today:
            invoice.status = Invoice.Status.OVERDUE
        else:
            invoice.status = Invoice.Status.UNPAID

        invoice.save(update_fields=["status", "updated_at"])

    BillingActivity.objects.create(
        user=performed_by,
        customer_id=customer_id,
        payment=payment,
        action=BillingActivity.ActionType.PAYMENT_RECORDED,
        description=(
            f"Payment {payment.payment_number} "
            f"of ₱{payment.amount:,.2f} was recorded."
        ),
        details={
            "payment_number": payment.payment_number,
            "amount": str(payment.amount),
            "payment_method": payment.payment_method,
            "reference_number": payment.reference_number,
            "allocations": [
                {
                    "invoice_id": item["invoice_id"],
                    "amount": str(item["amount"]),
                }
                for item in prepared_allocations
            ],
        },
    )
    return payment


@transaction.atomic
def void_invoice(invoice_id, reason, performed_by=None):
    """Void an unpaid invoice and preserve its audit history."""

    reason = (reason or "").strip()

    if not reason:
        raise ValidationError(
            "A reason is required to void an invoice."
        )

    invoice = (
        Invoice.objects
        .select_for_update()
        .select_related("customer")
        .get(pk=invoice_id)
    )

    if invoice.status == Invoice.Status.VOID:
        raise ValidationError("This invoice is already void.")

    if invoice.status == Invoice.Status.DRAFT:
        raise ValidationError(
            "Draft invoices cannot be voided using this operation."
        )

    if invoice.payment_allocations.exists():
        raise ValidationError(
            "This invoice has payment allocations. "
            "Reverse or resolve the allocated payments first."
        )

    if invoice.status not in (
        Invoice.Status.UNPAID,
        Invoice.Status.OVERDUE,
    ):
        raise ValidationError(
            "Only unpaid or overdue invoices can be voided."
        )

    old_status = invoice.status

    invoice.status = Invoice.Status.VOID
    invoice.notes = (
        f"{invoice.notes}\n\n"
        f"VOID REASON: {reason}"
    ).strip()

    invoice.save(update_fields=["status", "notes", "updated_at"])

    BillingActivity.objects.create(
        user=performed_by,
        customer=invoice.customer,
        invoice=invoice,
        action=BillingActivity.ActionType.INVOICE_VOIDED,
        description=(
            f"Invoice {invoice.invoice_number} was voided."
        ),
        details={
            "invoice_number": invoice.invoice_number,
            "previous_status": old_status,
            "new_status": invoice.status,
            "reason": reason,
            "total_amount": str(invoice.total_amount),
        },
    )

    return invoice


@transaction.atomic
def reverse_payment(payment_id, reason, performed_by=None):
    """Reverse a completed payment while preserving its audit history."""

    reason = (reason or "").strip()

    if not reason:
        raise ValidationError(
            "A reason is required to reverse a payment."
        )

    payment = (
        Payment.objects
        .select_for_update()
        .select_related("customer")
        .filter(pk=payment_id)
        .first()
    )

    if payment is None:
        raise ValidationError("Payment not found.")

    if payment.status == Payment.Status.REVERSED:
        raise ValidationError("This payment has already been reversed.")

    if payment.status != Payment.Status.COMPLETED:
        raise ValidationError(
            "Only completed payments can be reversed."
        )

    # Preserve the original payment allocations.
    allocations = list(
        PaymentAllocation.objects
        .filter(payment=payment)
        .order_by("invoice_id")
    )

    invoice_ids = sorted({
        allocation.invoice_id for allocation in allocations
    })

    # Lock all affected invoices in a consistent order.
    invoices = list(
        Invoice.objects
        .select_for_update()
        .filter(pk__in=invoice_ids)
        .order_by("pk")
    )

    old_status = payment.status

    payment.status = Payment.Status.REVERSED
    payment.notes = (
        f"{payment.notes}\n\n"
        f"REVERSAL REASON: {reason}"
    ).strip()

    payment.save(update_fields=["status", "notes"])

    today = timezone.localdate()

    for invoice in invoices:
        # Never change draft or void invoice statuses.
        if invoice.status in (
            Invoice.Status.DRAFT,
            Invoice.Status.VOID,
        ):
            continue

        # amount_paid now excludes the reversed payment.
        invoice.refresh_from_db()

        if invoice.balance <= 0:
            invoice.status = Invoice.Status.PAID
        elif invoice.amount_paid > 0:
            invoice.status = Invoice.Status.PARTIALLY_PAID
        elif invoice.due_date < today:
            invoice.status = Invoice.Status.OVERDUE
        else:
            invoice.status = Invoice.Status.UNPAID

        invoice.save(update_fields=["status", "updated_at"])

    BillingActivity.objects.create(
        user=performed_by,
        customer=payment.customer,
        payment=payment,
        action=BillingActivity.ActionType.PAYMENT_REVERSED,
        description=(
            f"Payment {payment.payment_number} "
            f"of ₱{payment.amount:,.2f} was reversed."
        ),
        details={
            "payment_number": payment.payment_number,
            "amount": str(payment.amount),
            "previous_status": old_status,
            "new_status": payment.status,
            "reason": reason,
            "affected_invoices": [
                {
                    "invoice_number": invoice.invoice_number,
                    "invoice_id": invoice.pk,
                }
                for invoice in invoices
            ],
            "allocations": [
                {
                    "invoice_id": allocation.invoice_id,
                    "amount": str(allocation.amount),
                }
                for allocation in allocations
            ],
        },
    )

    return payment
