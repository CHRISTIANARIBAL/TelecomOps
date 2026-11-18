
from django import forms
from django.utils import timezone
from .models import Subscription, Customer, InternetPlan, Invoice, Payment


class InvoiceGenerationForm(forms.Form):

    subscription = forms.ModelChoiceField(
        queryset=Subscription.objects.select_related(
            "customer",
            "internet_plan",
        ).all(),
        label="Customer Subscription",
    )

    billing_period_start = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    billing_period_end = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    issue_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    due_date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    discount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        initial=0,
        required=False,
    )

    tax_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        initial=0,
        required=False,
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean(self):
        cleaned_data = super().clean()

        start = cleaned_data.get("billing_period_start")
        end = cleaned_data.get("billing_period_end")
        issue = cleaned_data.get("issue_date")
        due = cleaned_data.get("due_date")

        if start and end and end < start:
            self.add_error(
                "billing_period_end",
                "Billing period end cannot be before its start.",
            )

        if issue and due and due < issue:
            self.add_error(
                "due_date",
                "Due date cannot be before issue date.",
            )

        return cleaned_data


class PaymentRecordingForm(forms.Form):

    customer = forms.ModelChoiceField(
        queryset=Customer.objects.filter(is_active=True),
        label="Customer",
    )

    invoice = forms.ModelChoiceField(
        queryset=Invoice.objects.exclude(
            status__in=[
                Invoice.Status.DRAFT,
                Invoice.Status.VOID,
            ]
        ).select_related("customer", "subscription"),
        label="Invoice",
    )

    payment_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        label="Payment Amount",
    )

    payment_method = forms.ChoiceField(
        choices=Payment.PaymentMethod.choices,
    )

    reference_number = forms.CharField(
        max_length=100,
        required=False,
        label="Transaction Reference",
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean(self):
        cleaned_data = super().clean()

        customer = cleaned_data.get("customer")
        invoice = cleaned_data.get("invoice")
        amount = cleaned_data.get("amount")

        if customer and invoice:
            if invoice.customer_id != customer.pk:
                self.add_error(
                    "invoice",
                    "This invoice does not belong to the selected customer.",
                )

        if invoice and amount is not None:
            if amount > invoice.balance:
                self.add_error(
                    "amount",
                    f"Payment cannot exceed the remaining balance "
                    f"of ₱{invoice.balance:,.2f}.",
                )

        return cleaned_data


class CustomerRegistrationForm(forms.ModelForm):

    class Meta:
        model = Customer

        fields = [
            "customer_type",
            "first_name",
            "last_name",
            "company_name",
            "contact_person",
            "tin",
            "contact_number",
            "email",
            "address",
            "city",
            "province",
            # "is_active",
        ]

        widgets = {
            "customer_type": forms.Select(attrs={
                "class": "form-input",
            }),

            "first_name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Enter first name",
            }),

            "last_name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Enter last name",
            }),

            "company_name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Enter company name",
            }),

            "contact_person": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Enter contact person",
            }),

            "tin": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Enter TIN",
            }),

            "contact_number": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "09XXXXXXXXX",
            }),

            "email": forms.EmailInput(attrs={
                "class": "form-input",
                "placeholder": "Enter email address",
            }),

            "address": forms.Textarea(attrs={
                "class": "form-input",
                "rows": 3,
                "placeholder": "Enter complete address",
            }),

            "city": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Enter city",
            }),

            "province": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Enter province",
            }),

            "is_active": forms.CheckboxInput(attrs={
                "class": "h-4 w-4 rounded border-slate-600 bg-[#080d19] text-blue-600 focus:ring-blue-500",
            }),
        }

class InternetPlanForm(forms.ModelForm):

    class Meta:
        model = InternetPlan

        fields = [
            "plan_name",
            "service_type",
            "description",
            "download_speed",
            "upload_speed",
            "burst_download_speed",
            "burst_upload_speed",
            "monthly_price",
            "is_active",
        ]

        widgets = {
            "plan_name": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. Sparrow",
            }),

            "service_type": forms.Select(attrs={
                "class": "form-input",
            }),

            "description": forms.Textarea(attrs={
                "class": "form-input",
                "rows": 3,
                "placeholder": "Describe this internet package",
            }),

            "download_speed": forms.NumberInput(attrs={
                "class": "form-input",
                "min": 1,
                "placeholder": "Committed download Mbps",
            }),

            "upload_speed": forms.NumberInput(attrs={
                "class": "form-input",
                "min": 1,
                "placeholder": "Committed upload Mbps",
            }),

            "burst_download_speed": forms.NumberInput(attrs={
                "class": "form-input",
                "min": 0,
                "placeholder": "Burst download Mbps",
            }),

            "burst_upload_speed": forms.NumberInput(attrs={
                "class": "form-input",
                "min": 0,
                "placeholder": "Burst upload Mbps",
            }),

            "monthly_price": forms.NumberInput(attrs={
                "class": "form-input",
                "min": 0,
                "step": "0.01",
                "placeholder": "Monthly subscription price",
            }),

            "is_active": forms.CheckboxInput(attrs={
                "class": "h-4 w-4 rounded border-slate-600 bg-[#080d19] text-blue-600 focus:ring-blue-500",
            }),
        }

    def clean(self):
        cleaned_data = super().clean()

        download = cleaned_data.get("download_speed")
        upload = cleaned_data.get("upload_speed")
        burst_download = cleaned_data.get("burst_download_speed")
        burst_upload = cleaned_data.get("burst_upload_speed")

        if download and burst_download and burst_download < download:
            self.add_error(
                "burst_download_speed",
                "Burst download cannot be lower than committed download speed.",
            )

        if upload and burst_upload and burst_upload < upload:
            self.add_error(
                "burst_upload_speed",
                "Burst upload cannot be lower than committed upload speed.",
            )

        return cleaned_data

    
class ClientSubscriptionForm(forms.ModelForm):

    class Meta:
        model = Subscription

        fields = [
            "internet_plan",
            "pppoe_username",
            "installation_date",
            "billing_date",
            "status",
            "notes",
        ]

        widgets = {
            "internet_plan": forms.Select(attrs={
                "class": "form-input",
            }),

            "pppoe_username": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "Enter PPPoE username",
            }),

            "installation_date": forms.DateInput(attrs={
                "class": "form-input pr-12",
                "type": "date",
            }),

            "billing_date": forms.DateInput(attrs={
                "class": "form-input pr-12",
                "type": "date",
            }),

            "status": forms.Select(attrs={
                "class": "form-input",
            }),

            "notes": forms.Textarea(attrs={
                "class": "form-input",
                "rows": 3,
                "placeholder": "Enter subscription notes",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["internet_plan"].queryset = (
            InternetPlan.objects.filter(is_active=True).order_by("monthly_price")
        )
