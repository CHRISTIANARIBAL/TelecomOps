from decimal import Decimal
from django import forms
from django.contrib.auth import get_user_model
from billing.models import Customer

User = get_user_model()

class SaleForm(forms.Form):

    customer = forms.ModelChoiceField(
        queryset=Customer.objects.filter(is_active=True),
        required=False,
        empty_label="Walk-in / Unregistered Customer",
    )

    released_by = forms.ModelChoiceField(
        queryset=User.objects.filter(
            role=User.Role.EMPLOYEE,
            is_active=True,
            is_approved=True,
            email_verified=True,
            approval_status=User.ApprovalStatus.APPROVED,
        ).order_by("first_name", "last_name"),
        required=False,
        empty_label="Select existing employee",
    )

    released_by_name = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter new employee's full name",
        }),
    )

    buyer_name = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter buyer's full name",
        }),
    )

    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
    )

    unit_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Optional transaction notes",
        }),
    )

    

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["released_by"].label_from_instance = (
            lambda employee: (
                f"{employee.get_full_name()} "
                f"(@{employee.username})"
            )
        )

    def clean(self):
        cleaned_data = super().clean()

        customer = cleaned_data.get("customer")
        buyer_name = (cleaned_data.get("buyer_name") or "").strip()

        released_by = cleaned_data.get("released_by")
        released_by_name = (
            cleaned_data.get("released_by_name") or ""
        ).strip()

        if not released_by and not released_by_name:
            self.add_error(
                "released_by",
                "Select an existing employee or enter a new employee name."
            )

        if released_by and released_by_name:
            self.add_error(
                "released_by_name",
                "Choose either an existing employee or a manually entered name."
            )

        cleaned_data["released_by_name"] = released_by_name

        if not customer and not buyer_name:
            self.add_error(
                "buyer_name",
                "Enter the walk-in buyer's name or select a registered customer.",
            )

        if customer and not buyer_name:
            buyer_name = (
                customer.company_name
                or f"{customer.first_name} {customer.last_name}".strip()
            )

        cleaned_data["buyer_name"] = buyer_name

        return cleaned_data


class SaleEditForm(forms.Form):

    customer = forms.ModelChoiceField(
        queryset=Customer.objects.filter(is_active=True),
        required=False,
        empty_label="Walk-in / Unregistered Customer",
    )

    buyer_name = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter buyer's full name",
        }),
    )

    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
    )

    unit_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": "Optional transaction notes",
        }),
    )

    def clean(self):
        cleaned_data = super().clean()

        customer = cleaned_data.get("customer")
        buyer_name = (cleaned_data.get("buyer_name") or "").strip()

        if not customer and not buyer_name:
            self.add_error(
                "buyer_name",
                "Enter the walk-in buyer's name or select a registered customer.",
            )

        if customer and not buyer_name:
            buyer_name = (
                customer.company_name
                or f"{customer.first_name} {customer.last_name}".strip()
            )

        cleaned_data["buyer_name"] = buyer_name

        return cleaned_data
