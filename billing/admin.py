from django.urls import path, reverse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from .forms import InvoiceGenerationForm, PaymentRecordingForm
from .services import generate_invoice, record_payment, void_invoice, reverse_payment

from django.contrib import admin
from .models import Customer, InternetPlan, Subscription, Invoice, InvoiceItem, Payment, PaymentAllocation, BillingActivity


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "customer_id",
        "customer_type",
        "first_name",
        "last_name",
        "company_name",
        "contact_number",
        "is_active",
        "created_at",
    )
    list_filter = ("customer_type", "is_active")
    search_fields = (
        "customer_id",
        "first_name",
        "last_name",
        "company_name",
        "contact_number",
        "email",
    )
    readonly_fields = ("customer_id", "created_at", "updated_at")
    list_per_page = 25

    def has_delete_permission(self, request, obj=None):
        return False
    
    def save_model(self, request, obj, form, change):
        if change:
            action = BillingActivity.ActionType.CUSTOMER_UPDATED
            description = (
                f"Customer {obj.customer_id} information was updated."
            )
        else:
            action = BillingActivity.ActionType.CUSTOMER_CREATED
            description = (
                f"Customer {obj.customer_id} was created."
            )

        super().save_model(request, obj, form, change)

        BillingActivity.objects.create(
            user=request.user,
            customer=obj,
            action=action,
            description=description,
            details={
                "customer_id": obj.customer_id,
                "customer_type": obj.customer_type,
                "first_name": obj.first_name,
                "last_name": obj.last_name,
                "company_name": obj.company_name,
                "email": obj.email,
                "contact_number": obj.contact_number,
            },
        )


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "subscription_number",
        "customer",
        "internet_plan",
        "pppoe_username",
        "billing_date",
        "status",
        "installation_date",
    )

    list_filter = ("status", "internet_plan")

    search_fields = (
        "subscription_number",
        "pppoe_username",
        "customer__customer_id",
        "customer__first_name",
        "customer__last_name",
        "customer__company_name",
    )

    readonly_fields = (
        "subscription_number",
        "created_at",
        "updated_at",
    )

    list_per_page = 25

    actions = [
        "suspend_subscriptions",
        "reactivate_subscriptions",
    ]

    def has_delete_permission(self, request, obj=None):
        return False
    def save_model(self, request, obj, form, change):
        old_status = None

        if change:
            old_status = (
                Subscription.objects
                .get(pk=obj.pk)
                .status
            )

        super().save_model(request, obj, form, change)

        if not change:
            action = BillingActivity.ActionType.SUBSCRIPTION_CREATED
            description = (
                f"Subscription {obj.subscription_number} was created."
            )

        else:
            action = BillingActivity.ActionType.SUBSCRIPTION_UPDATED
            description = (
                f"Subscription {obj.subscription_number} was updated."
            )

        BillingActivity.objects.create(
            user=request.user,
            customer=obj.customer,
            action=action,
            description=description,
            details={
                "subscription_number": obj.subscription_number,
                "pppoe_username": obj.pppoe_username,
                "internet_plan": str(obj.internet_plan),
                "old_status": old_status,
                "new_status": obj.status,
            },
        )

    @admin.action(description="Suspend selected subscriptions")
    def suspend_subscriptions(self, request, queryset):
        count = 0

        for subscription in queryset.select_related("customer"):
            if subscription.status in (
                Subscription.Status.SUSPENDED,
                Subscription.Status.CANCELLED,
            ):
                continue

            old_status = subscription.status

            subscription.status = Subscription.Status.SUSPENDED
            subscription.save(update_fields=["status", "updated_at"])

            BillingActivity.objects.create(
                user=request.user,
                customer=subscription.customer,
                action=BillingActivity.ActionType.SUBSCRIPTION_SUSPENDED,
                description=(
                    f"Subscription {subscription.subscription_number} "
                    "was suspended by an administrator."
                ),
                details={
                    "subscription_number": subscription.subscription_number,
                    "pppoe_username": subscription.pppoe_username,
                    "old_status": old_status,
                    "new_status": subscription.status,
                    "reason": "Administrator action",
                },
            )

            count += 1

        self.message_user(
            request,
            f"{count} subscription(s) suspended.",
            messages.SUCCESS,
        )

    @admin.action(description="Reactivate selected subscriptions")
    def reactivate_subscriptions(self, request, queryset):
        count = 0

        for subscription in queryset.select_related("customer"):
            if subscription.status != Subscription.Status.SUSPENDED:
                continue

            old_status = subscription.status

            subscription.status = Subscription.Status.ACTIVE
            subscription.save(update_fields=["status", "updated_at"])

            BillingActivity.objects.create(
                user=request.user,
                customer=subscription.customer,
                action=BillingActivity.ActionType.SUBSCRIPTION_REACTIVATED,
                description=(
                    f"Subscription {subscription.subscription_number} "
                    "was reactivated by an administrator."
                ),
                details={
                    "subscription_number": subscription.subscription_number,
                    "pppoe_username": subscription.pppoe_username,
                    "old_status": old_status,
                    "new_status": subscription.status,
                    "reason": "Administrator action",
                },
            )

            count += 1

        self.message_user(
            request,
            f"{count} subscription(s) reactivated.",
            messages.SUCCESS,
        )


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "customer",
        "subscription",
        "issue_date",
        "due_date",
        "total_amount",
        "status",
    )
    list_filter = ("status", "issue_date", "due_date")
    search_fields = (
        "invoice_number",
        "customer__customer_id",
        "customer__first_name",
        "customer__last_name",
        "customer__company_name",
    )
    readonly_fields = ("invoice_number", "created_at", "updated_at", "void_invoice_link",)
    inlines = [InvoiceItemInline]
    list_per_page = 25

    change_list_template = "admin/billing/invoice/change_list.html"

    def has_delete_permission(self, request, obj=None):
        return False
    def void_invoice_link(self, obj):
        if not obj or not obj.pk:
            return "-"

        if obj.status not in (
            Invoice.Status.UNPAID,
            Invoice.Status.OVERDUE,
        ):
            return "Not available for this invoice status."

        if obj.payment_allocations.exists():
            return "Cannot void: payment allocations exist."

        url = reverse(
            "admin:billing_invoice_void",
            args=[obj.pk],
        )

        return format_html(
            '<a class="button" style="background:#ba2121; color:white;" href="{}">'
            'Void Invoice</a>',
            url,
        )

    void_invoice_link.short_description = "Invoice Actions"
    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "generate/",
                self.admin_site.admin_view(
                    self.generate_invoice_view
                ),
                name="billing_invoice_generate",
            ),
            path(
                "<path:object_id>/void/",
                self.admin_site.admin_view(
                    self.void_invoice_view
                ),
                name="billing_invoice_void",
            ),
        ]

        return custom_urls + urls

    def generate_invoice_view(self, request):

        if request.method == "POST":
            form = InvoiceGenerationForm(request.POST)

            if form.is_valid():
                data = form.cleaned_data

                try:
                    invoice = generate_invoice(
                        subscription_id=data["subscription"].pk,
                        billing_period_start=data["billing_period_start"],
                        billing_period_end=data["billing_period_end"],
                        issue_date=data["issue_date"],
                        due_date=data["due_date"],
                        discount=data["discount"] or 0,
                        tax_amount=data["tax_amount"] or 0,
                        notes=data["notes"],
                        performed_by=request.user,
                    )

                    messages.success(
                        request,
                        f"Invoice {invoice.invoice_number} "
                        "was successfully generated.",
                    )

                    return redirect(
                        reverse(
                            "admin:billing_invoice_change",
                            args=[invoice.pk],
                        )
                    )

                except ValidationError as exc:
                    form.add_error(None, exc)

        else:
            form = InvoiceGenerationForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Generate Customer Invoice",
            "form": form,
            "opts": self.model._meta,
        }

        return render(
            request,
            "admin/billing/invoice/generate.html",
            context,
        )

    def void_invoice_view(self, request, object_id):
        invoice = self.get_object(request, object_id)

        if invoice is None:
            self.message_user(
                request,
                "Invoice not found.",
                messages.ERROR,
            )
            return redirect("admin:billing_invoice_changelist")

        if request.method == "POST":
            reason = request.POST.get("reason", "").strip()

            try:
                void_invoice(
                    invoice_id=invoice.pk,
                    reason=reason,
                    performed_by=request.user,
                )

                self.message_user(
                    request,
                    f"Invoice {invoice.invoice_number} was successfully voided.",
                    messages.SUCCESS,
                )

                return redirect(
                    "admin:billing_invoice_change",
                    object_id=invoice.pk,
                )

            except ValidationError as exc:
                self.message_user(
                    request,
                    " ".join(exc.messages),
                    messages.ERROR,
                )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "invoice": invoice,
            "title": f"Void Invoice: {invoice.invoice_number}",
        }

        return render(
            request,
            "admin/billing/invoice/void_invoice.html",
            context,
        )

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "payment_number",
        "customer",
        "payment_date",
        "amount",
        "payment_method",
        "reference_number",
        "status",
    )
    list_filter = ("payment_method", "status", "payment_date")
    search_fields = (
        "payment_number",
        "reference_number",
        "customer__customer_id",
        "customer__first_name",
        "customer__last_name",
        "customer__company_name",
    )
    readonly_fields = ("payment_number", "created_at", "reverse_payment_link")

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == Payment.Status.REVERSED:
            return tuple(
                field.name for field in self.model._meta.fields
            ) + ("reverse_payment_link",)

        return super().get_readonly_fields(request, obj)

    list_per_page = 25

    
    change_list_template = "admin/billing/payment/change_list.html"

    def has_delete_permission(self, request, obj=None):
        return False

    def reverse_payment_link(self, obj):
        if not obj or not obj.pk:
            return "-"

        if obj.status != Payment.Status.COMPLETED:
            return "Reversal not available for this payment."

        url = reverse(
            "admin:billing_payment_reverse",
            args=[obj.pk],
        )

        return format_html(
            '<a class="button" style="background:#ba2121; color:white;" href="{}">'
            'Reverse Payment</a>',
            url,
        )

    reverse_payment_link.short_description = "Payment Actions"

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "record/",
                self.admin_site.admin_view(
                    self.record_payment_view
                ),
                name="billing_payment_record",
            ),
            path(
                "<path:object_id>/reverse/",
                self.admin_site.admin_view(
                    self.reverse_payment_view
                ),
                name="billing_payment_reverse",
            ),
        ]

        return custom_urls + urls

    def record_payment_view(self, request):

        if request.method == "POST":
            form = PaymentRecordingForm(request.POST)

            if form.is_valid():
                data = form.cleaned_data

                try:
                    payment = record_payment(
                        customer_id=data["customer"].pk,
                        payment_date=data["payment_date"],
                        amount=data["amount"],
                        payment_method=data["payment_method"],
                        allocations=[
                            {
                                "invoice_id": data["invoice"].pk,
                                "amount": data["amount"],
                            }
                        ],
                        reference_number=data["reference_number"],
                        notes=data["notes"],
                        performed_by=request.user,
                    )

                    messages.success(
                        request,
                        f"Payment {payment.payment_number} "
                        "was successfully recorded.",
                    )

                    return redirect(
                        reverse(
                            "admin:billing_payment_change",
                            args=[payment.pk],
                        )
                    )

                except ValidationError as exc:
                    form.add_error(None, exc)

        else:
            form = PaymentRecordingForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Record Customer Payment",
            "form": form,
            "opts": self.model._meta,
        }

        return render(
            request,
            "admin/billing/payment/record.html",
            context,
        )

    def reverse_payment_view(self, request, object_id):
        payment = self.get_object(request, object_id)

        if payment is None:
            self.message_user(
                request,
                "Payment not found.",
                messages.ERROR,
            )
            return redirect("admin:billing_payment_changelist")

        if request.method == "POST":
            reason = request.POST.get("reason", "").strip()

            try:
                reverse_payment(
                    payment_id=payment.pk,
                    reason=reason,
                    performed_by=request.user,
                )

                self.message_user(
                    request,
                    f"Payment {payment.payment_number} was successfully reversed.",
                    messages.SUCCESS,
                )

                return redirect(
                    "admin:billing_payment_change",
                    object_id=payment.pk,
                )

            except ValidationError as exc:
                self.message_user(
                    request,
                    " ".join(exc.messages),
                    messages.ERROR,
                )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "payment": payment,
            "title": f"Reverse Payment: {payment.payment_number}",
        }

        return render(
            request,
            "admin/billing/payment/reverse_payment.html",
            context,
        )

@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ("payment", "invoice", "amount", "created_at")
    list_filter = ("created_at",)
    search_fields = (
        "payment__payment_number",
        "invoice__invoice_number",
    )
    list_per_page = 25

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(BillingActivity)
class BillingActivityAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "action",
        "customer",
        "invoice",
        "payment",
    )
    list_filter = ("action", "created_at")
    search_fields = (
        "description",
        "customer__customer_id",
        "invoice__invoice_number",
        "payment__payment_number",
        "user__username",
    )
    readonly_fields = (
        "user",
        "customer",
        "invoice",
        "payment",
        "action",
        "description",
        "details",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
