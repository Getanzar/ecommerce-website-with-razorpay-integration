from django import forms

from .models import GroceryOrder, GroceryProduct, GroceryProductOption, GroceryStore
from delivery.forms import RequiredGPSMixin


class GroceryStoreForm(RequiredGPSMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not field.widget.is_hidden and not isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                field.widget.attrs["class"] = "form-control"

    def clean_image(self):
        from accounts.seller_profile import validate_store_image
        return validate_store_image(self.cleaned_data.get("image"))

    class Meta:
        model = GroceryStore
        fields = ("name", "description", "image", "address", "pincode", "latitude", "longitude", "gps_accuracy_meters", "phone", "minimum_order", "delivery_fee", "estimated_delivery_minutes", "service_areas")
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "address": forms.Textarea(attrs={"rows": 2}), "service_areas": forms.CheckboxSelectMultiple()}


class GroceryProductForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("unit", "mrp", "price", "stock"):
            self.fields[name].label = {"unit": "First pack size", "mrp": "First pack MRP", "price": "First pack selling price", "stock": "First pack stock"}[name]
        self.fields["unit"].help_text = "For example: 500 g, 1 kg, 5 kg, 500 ml, or pack of 6. Add other sizes below."
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-control"
    class Meta:
        model = GroceryProduct
        fields = ("category", "name", "description", "brand", "image", "unit", "mrp", "price", "gst_rate", "stock", "is_active", "is_perishable")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("price") and cleaned.get("mrp") and cleaned["price"] > cleaned["mrp"]:
            self.add_error("price", "Selling price cannot exceed MRP.")
        for name in ("price", "mrp"):
            if cleaned.get(name) is not None and cleaned[name] <= 0:
                self.add_error(name, "Enter an amount greater than zero.")
        if self.instance.pk and cleaned.get("unit") and self.instance.options.filter(is_default=False, is_active=True, unit__iexact=cleaned["unit"]).exists():
            self.add_error("unit", "This pack size already exists below. Choose a different first pack label.")
        return cleaned


class GroceryProductOptionForm(forms.ModelForm):
    class Meta:
        model = GroceryProductOption
        fields = ("unit", "mrp", "price", "stock", "is_active")
        widgets = {"unit": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 1 kg"}), "price": forms.NumberInput(attrs={"class": "form-control", "min": "0.01", "step": "0.01"}), "mrp": forms.NumberInput(attrs={"class": "form-control", "min": "0.01", "step": "0.01"}), "stock": forms.NumberInput(attrs={"class": "form-control", "min": "0"}), "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"})}

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("price") is not None and cleaned.get("mrp") is not None and cleaned["price"] > cleaned["mrp"]:
            self.add_error("price", "Selling price cannot exceed MRP.")
        return cleaned


class BaseGroceryOptionFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        labels = {self.instance.unit.strip().casefold()}
        for form in self.forms:
            data = form.cleaned_data
            option = data.get("id")
            if option and (option.product_id != self.instance.pk or option.is_default):
                raise forms.ValidationError("That pack size does not belong to this product.")
            if not data or data.get("DELETE") or not data.get("is_active"):
                continue
            label = data["unit"].strip().casefold()
            if label in labels:
                raise forms.ValidationError("Each active pack size must have a different label.")
            labels.add(label)

    def save(self, commit=True):
        instances = super().save(commit=False)
        if commit:
            for removed in self.deleted_objects:
                removed.is_active = False
                removed.save(update_fields=["is_active"])
            for instance in instances:
                instance.product = self.instance
                instance.save()
        return instances


GroceryOptionFormSet = forms.inlineformset_factory(
    GroceryProduct, GroceryProductOption, form=GroceryProductOptionForm,
    formset=BaseGroceryOptionFormSet, extra=0, can_delete=True, max_num=19, absolute_max=38, validate_max=True,
)


class GroceryCheckoutForm(RequiredGPSMixin, forms.ModelForm):
    class Meta:
        model = GroceryOrder
        fields = ("full_name", "phone", "address", "city", "state", "pincode", "latitude", "longitude", "gps_accuracy_meters", "substitution_preference", "payment_method")
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}

    def clean_pincode(self):
        value = self.cleaned_data["pincode"].strip()
        if not value.isdigit() or len(value) != 6:
            raise forms.ValidationError("Enter a valid 6-digit pincode.")
        return value
