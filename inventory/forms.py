
from django import forms
from django.db.models import Q

from .models import Product, Category, ProductImage

class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image"]

class ProductForm(forms.ModelForm):

    # Main category selection
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(
            is_active=True,
            parent__isnull=True
        ),
        required=False,
        empty_label="Select a main category"
    )

    # Optional subcategory selection
    subcategory = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        required=False,
        empty_label="Select a subcategory (optional)"
    )

    # Create a new main category
    new_category_name = forms.CharField(
        max_length=150,
        required=False
    )

    new_category_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2})
    )
    # Create a new subcategory under the selected or newly created main category
    new_subcategory_name = forms.CharField(
        max_length=150,
        required=False
    )

    # Initial stock
    initial_stock = forms.IntegerField(
        min_value=0,
        initial=0,
        required=True
    )

    class Meta:
        model = Product

        fields = [
            "sku",
            "name",
            "image",
            "category",
            "subcategory",
            "tracking_type",
            "description",
            "unit_of_measure",
            "cost_price",
            "selling_price",
            "minimum_stock",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Preserve existing category when editing a product.
        current_category_id = (
            self.data.get("category")
            if self.is_bound
            else self.instance.category_id
        )

        current_subcategory_id = (
            self.data.get("subcategory")
            if self.is_bound
            else self.instance.subcategory_id
        )

        # Main category choices.
        category_queryset = Category.objects.filter(
            is_active=True,
            parent__isnull=True
        )

        # Allow the existing category to remain selectable
        # when editing a product.
        if self.instance.pk and self.instance.category_id:
            category_queryset = Category.objects.filter(
                Q(is_active=True, parent__isnull=True) |
                Q(pk=self.instance.category_id)
            )

        self.fields["category"].queryset = category_queryset

        # Subcategories belonging to the selected main category.
        if current_category_id:
            subcategory_queryset = Category.objects.filter(
                parent_id=current_category_id,
                is_active=True
            )

            # Preserve the existing subcategory when editing.
            if self.instance.pk and self.instance.subcategory_id:
                subcategory_queryset = Category.objects.filter(
                    Q(
                        parent_id=current_category_id,
                        is_active=True
                    ) |
                    Q(pk=self.instance.subcategory_id)
                )

            self.fields["subcategory"].queryset = subcategory_queryset

        # Existing placeholders
        self.fields["sku"].widget.attrs.update({
            "placeholder": "Enter product SKU"
        })

        self.fields["name"].widget.attrs.update({
            "placeholder": "Enter product name"
        })

        self.fields["unit_of_measure"].widget.attrs.update({
            "placeholder": "e.g. pcs, meters, boxes"
        })

        self.fields["description"].widget.attrs.update({
            "placeholder": "Enter product description"
        })

        self.fields["new_category_name"].widget.attrs.update({
            "placeholder": "Enter new category name"
        })

        self.fields["new_category_description"].widget.attrs.update({
            "placeholder": "Optional category description"
        })

        self.fields["new_subcategory_name"].widget.attrs.update({
            "placeholder": "Enter new subcategory name"
        })

        self.fields["cost_price"].widget.attrs.update({
            "placeholder": "0.00",
            "min": "0",
            "step": "0.01"
        })

        self.fields["selling_price"].widget.attrs.update({
            "placeholder": "0.00",
            "min": "0",
            "step": "0.01"
        })

    def clean_sku(self):
        sku = self.cleaned_data["sku"].strip()

        duplicate = Product.objects.filter(
            sku__iexact=sku
        )

        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)

        if duplicate.exists():
            raise forms.ValidationError(
                "This SKU is already registered."
            )

        return sku

    def clean_new_category_name(self):
        return self.cleaned_data["new_category_name"].strip()

    def clean_new_subcategory_name(self):
        return self.cleaned_data["new_subcategory_name"].strip()

    def clean(self):
        cleaned_data = super().clean()

        category = cleaned_data.get("category")
        subcategory = cleaned_data.get("subcategory")
        new_category_name = cleaned_data.get("new_category_name")
        new_subcategory_name = cleaned_data.get("new_subcategory_name")

        # Main category validation
        if not category and not new_category_name:
            self.add_error(
                "category",
                "Select an existing category or create a new one."
            )

        if category and new_category_name:
            self.add_error(
                "new_category_name",
                "Please select an existing category OR create a new one, not both."
            )

        # New category validation
        if new_category_name:
            existing_category = Category.objects.filter(
                name__iexact=new_category_name
            ).first()

            if existing_category:
                if existing_category.is_active:
                    self.add_error(
                        "new_category_name",
                        "This category already exists. Please select it from the existing category dropdown."
                    )
                else:
                    self.add_error(
                        "new_category_name",
                        "This category already exists but is inactive. Reactivate it before using it."
                    )

            if subcategory:
                self.add_error(
                    "subcategory",
                    "A subcategory cannot be selected when creating a new main category."
                )

        # Subcategory validation
        if subcategory and category:
            if subcategory.parent_id != category.id:
                self.add_error(
                    "subcategory",
                    "The selected subcategory does not belong to the selected main category."
                )
        # New subcategory validation
        if new_subcategory_name:

            # Prevent creating a new subcategory without a main category.
            if not category and not new_category_name:
                self.add_error(
                    "new_subcategory_name",
                    "Select or create a main category before adding a subcategory."
                )

            # Prevent selecting an existing subcategory and creating another one.
            if subcategory:
                self.add_error(
                    "new_subcategory_name",
                    "Select an existing subcategory OR create a new one, not both."
                )

            # Prevent duplicate subcategory names.
            duplicate_subcategory = Category.objects.filter(
                name__iexact=new_subcategory_name
            )

            if duplicate_subcategory.exists():
                self.add_error(
                    "new_subcategory_name",
                    "This category name already exists. Please use a different name."
                )

        # Price validation
        cost_price = cleaned_data.get("cost_price")
        selling_price = cleaned_data.get("selling_price")

        if cost_price is not None and cost_price < 0:
            self.add_error(
                "cost_price",
                "Cost price cannot be negative."
            )

        if selling_price is not None and selling_price < 0:
            self.add_error(
                "selling_price",
                "Selling price cannot be negative."
            )

        return cleaned_data


class ProductUpdateForm(ProductForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Stock must be managed separately.
        self.fields.pop("initial_stock", None)


class CategoryForm(forms.ModelForm):

    parent = forms.ModelChoiceField(
        queryset=Category.objects.filter(
            is_active=True,
            parent__isnull=True
        ),
        required=False,
        empty_label="Main Category (No Parent)"
    )

    class Meta:
        model = Category

        fields = [
            "name",
            "parent",
            "description",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Preserve an existing parent even if it was deactivated.
        if self.instance.pk and self.instance.parent_id:
            self.fields["parent"].queryset = Category.objects.filter(
                Q(is_active=True, parent__isnull=True) |
                Q(pk=self.instance.parent_id)
            )

        self.fields["name"].widget.attrs.update({
            "placeholder": "Enter category name"
        })

        self.fields["description"].widget.attrs.update({
            "placeholder": "Enter category description (optional)",
            "rows": 3,
        })


    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        duplicate = Category.objects.filter(
            name__iexact=name
        )

        if self.instance.pk:
            duplicate = duplicate.exclude(
                pk=self.instance.pk
            )

        if duplicate.exists():
            raise forms.ValidationError(
                "This category name is already registered."
            )

        return name

    def clean(self):
        cleaned_data = super().clean()

        parent = cleaned_data.get("parent")

        # Prevent a category with existing subcategories
        # from becoming a subcategory.
        if (
            self.instance.pk
            and parent
            and self.instance.subcategories.exists()
        ):
            self.add_error(
                "parent",
                "This category already has subcategories and cannot become a subcategory."
            )

        # Prevent selecting itself as its own parent.
        if self.instance.pk and parent:
            if parent.pk == self.instance.pk:
                self.add_error(
                    "parent",
                    "A category cannot be its own parent."
                )

        return cleaned_data
