from django import forms

from products.models import Product
from products.models import ProductVariant


class SellerProductForm(forms.ModelForm):
    """The initial seller catalog form. Admin approval is required before listing."""

    back_image = forms.ImageField(
        label="Back photo",
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": "image/*"}
        ),
        help_text="Upload a clear photo of the back of the product.",
    )

    class Meta:
        model = Product
        fields = (
            "category",
            "subcategory",
            "name",
            "description",
            "price",
            "gst_rate",
            "package_weight_grams",
            "package_length_cm",
            "package_width_cm",
            "package_height_cm",
            "image",
            "product_type",
        )
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "subcategory": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 4}
            ),
            "price": forms.NumberInput(
                attrs={"class": "form-control", "min": "0.01", "step": "0.01"}
            ),
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "product_type": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subcategory"].required = False
        self.fields["subcategory"].queryset = self.fields[
            "subcategory"
        ].queryset.select_related("category").order_by("name")
        self.fields["price"].label = "Your selling price"
        self.fields["image"].label = "Main product picture"
        self.fields["image"].widget.attrs.update(
            {"accept": "image/*"}
        )
        self.fields["image"].required = True
        self.fields["description"].required = True

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        subcategory = cleaned_data.get("subcategory")

        if subcategory and category and subcategory.category_id != category.id:
            self.add_error("subcategory", "Choose a subcategory from the selected category.")

        return cleaned_data


class SellerProductEditForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            "name", "description", "price", "gst_rate", "package_weight_grams",
            "package_length_cm", "package_width_cm", "package_height_cm", "image",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "price": forms.NumberInput(attrs={"class": "form-control", "min": "0.01", "step": "0.01"}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
        }


class SellerVariantStockForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ("stock", "price", "sku")
        widgets = {
            "stock": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "price": forms.NumberInput(attrs={"class": "form-control", "min": "0.01", "step": "0.01"}),
            "sku": forms.TextInput(attrs={"class": "form-control"}),
        }
