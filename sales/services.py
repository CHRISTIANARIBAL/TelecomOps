
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from inventory.models import Product, StockBalance
from .models import Sale, SaleItem, SaleEditHistory


@transaction.atomic
def create_sale(
    *,
    product_id,
    quantity,
    unit_price,
    buyer_name,
    processed_by,
    released_by,
    customer=None,
    notes="",
):
    # Lock the product record.
    product = Product.objects.select_for_update().get(
        pk=product_id
    )

    # Do not allow inactive products or unavailable categories.
    if not product.is_active:
        raise ValidationError("This product is inactive.")

    if not product.category.is_active:
        raise ValidationError(
            "This product belongs to an inactive category."
        )

    if product.category.parent_id and not product.category.parent.is_active:
        raise ValidationError(
            "This product belongs to an inactive parent category."
        )

    # Serialized products require individual serial-number tracking.
    if product.tracking_type == Product.TrackingType.SERIALIZED:
        raise ValidationError(
            "Serialized products cannot be sold through quantity-based sales."
        )

    if quantity < 1:
        raise ValidationError("Sale quantity must be at least 1.")

    # Lock the stock balance to prevent concurrent overselling.
    stock = StockBalance.objects.select_for_update().get(
        product=product
    )

    if stock.available_stock < quantity:
        raise ValidationError(
            f"Insufficient stock. Available quantity: {stock.available_stock}."
        )

    unit_price = Decimal(str(unit_price))

    if unit_price < 0:
        raise ValidationError("Selling price cannot be negative.")

    subtotal = unit_price * quantity

    # Create the transaction header.
    sale = Sale.objects.create(
        customer=customer,
        buyer_name=buyer_name,
        processed_by=processed_by,
        released_by=released_by,
        subtotal=subtotal,
        discount=Decimal("0.00"),
        total_amount=subtotal,
        notes=notes,
    )

    # Record the product sold.
    SaleItem.objects.create(
        sale=sale,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
        amount=subtotal,
    )

    # Deduct sold quantity without changing reserved stock.
    stock.quantity_on_hand = F("quantity_on_hand") - quantity
    stock.save(update_fields=["quantity_on_hand", "updated_at"])

    return sale


@transaction.atomic
def update_sale(
    *,
    sale_id,
    quantity,
    unit_price,
    buyer_name,
    customer=None,
    notes="",
    edited_by,
):
    # Retrieve the transaction and its existing product.
    sale = (
        Sale.objects
        .select_related("customer", "processed_by")
        .get(pk=sale_id)
    )

    if sale.status != Sale.Status.COMPLETED:
        raise ValidationError("Only completed sales can be edited.")

    # This workflow currently supports one product per transaction.
    items = list(sale.items.all())

    if len(items) != 1:
        raise ValidationError(
            "This transaction cannot be edited because it does not contain exactly one product."
        )

    item = items[0]
    product = Product.objects.get(pk=item.product_id)

    if product.tracking_type != Product.TrackingType.QUANTITY:
        raise ValidationError(
            "Only quantity-based products can be edited through this workflow."
        )

    if quantity < 1:
        raise ValidationError("Quantity must be at least 1.")

    unit_price = Decimal(str(unit_price))

    if unit_price < 0:
        raise ValidationError("Unit price cannot be negative.")

    old_quantity = item.quantity
    old_unit_price = item.unit_price
    old_buyer_name = sale.buyer_name

    quantity_difference = quantity - old_quantity

    stock = StockBalance.objects.get(product=product)
    # Deduct only the additional quantity required.
    if quantity_difference > 0:

        # Additional quantities can only be sold if the product
        # and its category hierarchy are active.
        if not product.is_active:
            raise ValidationError("This product is inactive.")

        if not product.category.is_active:
            raise ValidationError(
                "This product belongs to an inactive category."
            )

        if product.category.parent_id and not product.category.parent.is_active:
            raise ValidationError(
                "This product belongs to an inactive parent category."
        )

        updated = StockBalance.objects.filter(
            pk=stock.pk,
            quantity_on_hand__gte=(
                F("quantity_reserved") + quantity_difference
            ),
        ).update(
            quantity_on_hand=F("quantity_on_hand") - quantity_difference
        )

        if updated == 0:
            stock.refresh_from_db()
            raise ValidationError(
                f"Insufficient available stock. Available quantity: {stock.available_stock}."
            )

    # Restore stock if the revised quantity is lower.
    elif quantity_difference < 0:

        StockBalance.objects.filter(
            pk=stock.pk
        ).update(
            quantity_on_hand=F("quantity_on_hand") - quantity_difference
        )

    # Calculate revised transaction totals.
    subtotal = quantity * unit_price
    discount = sale.discount

    if discount > subtotal:
        raise ValidationError(
            "The existing discount cannot exceed the revised subtotal."
        )

    total_amount = subtotal - discount

    # Update the sale item.
    item.quantity = quantity
    item.unit_price = unit_price
    item.amount = subtotal
    item.save(
        update_fields=["quantity", "unit_price", "amount"]
    )

    # Update transaction information.
    sale.customer = customer
    sale.buyer_name = buyer_name
    sale.notes = notes
    sale.subtotal = subtotal
    sale.total_amount = total_amount

    sale.save(
        update_fields=[
            "customer",
            "buyer_name",
            "notes",
            "subtotal",
            "total_amount",
        ]
    )

    # Record the transaction changes.
    description = (
        f"Product: {product.name}\n"
        f"Quantity: {old_quantity} → {quantity}\n"
        f"Unit price: {old_unit_price} → {unit_price}\n"
        f"Buyer: {old_buyer_name} → {buyer_name}"
    )

    SaleEditHistory.objects.create(
        sale=sale,
        edited_by=edited_by,
        description=description,
    )

    return sale
