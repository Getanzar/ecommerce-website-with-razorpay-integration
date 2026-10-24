from django import forms
from django.core.validators import MinValueValidator
from products.models import Product
from products.electronics import ELECTRONICS
from .forms import ProductAudienceMixin

class ElectronicsProductForm(ProductAudienceMixin, forms.ModelForm):
    brand = forms.CharField(max_length=100)
    model_number = forms.CharField(max_length=100)
    warranty = forms.CharField(max_length=200, help_text="State the warranty period and provider, or no warranty.")
    color = forms.CharField(max_length=50)
    quantity = forms.IntegerField(min_value=0)

    class Meta:
        model = Product
        fields = ("name", "description", "price", "gst_rate", "image", "package_weight_grams", "package_length_cm", "package_width_cm", "package_height_cm")

    def __init__(self, *args, kind, **kwargs):
        if not kwargs.get("instance"):
            kwargs["instance"] = Product(category_id=None)
        self.kind = kind
        super().__init__(*args, **kwargs)
        self.fields["image"].required = not self.instance.pk
        self.fields["description"].required = True
        self.fields["price"].min_value = 0.01
        self.fields["price"].validators.append(MinValueValidator(0.01))
        if not self.instance.pk and "gst_rate" in self.fields:
            self.fields["gst_rate"].initial = None
        for name in ("package_weight_grams", "package_length_cm", "package_width_cm", "package_height_cm"):
            self.fields[name].validators.append(MinValueValidator(1))
        for label in ELECTRONICS[kind]["fields"]:
            self.fields["spec_" + label.lower().replace(" ", "_")] = forms.CharField(label=label, max_length=200)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"
            if self.instance.pk:
                field.initial = self.instance.specifications.get(field.label, self.instance.specifications.get(name, field.initial))
        if self.instance.pk:
            self.fields["quantity"].initial = self.instance.stock
            self.fields["quantity"].disabled = True
            self.fields["quantity"].help_text = "Update quantities through Manage inventory."

    def save(self, commit=True):
        product = super().save(commit=False)
        product.product_type = self.kind
        product.stock = self.cleaned_data["quantity"]
        product.specifications = {self.fields[k].label if k.startswith("spec_") else k: v for k, v in self.cleaned_data.items() if k.startswith("spec_") or k in ("brand", "model_number", "warranty", "color")}
        if commit:
            product.save()
        return product
