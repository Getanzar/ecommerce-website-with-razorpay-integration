from django import forms

from .models import GroceryOrder, GroceryProduct, GroceryStore
from delivery.forms import RequiredGPSMixin


class GroceryStoreForm(RequiredGPSMixin, forms.ModelForm):
    class Meta:
        model = GroceryStore
        fields = ("name", "description", "image", "address", "pincode", "latitude", "longitude", "gps_accuracy_meters", "phone", "minimum_order", "delivery_fee", "estimated_delivery_minutes", "service_areas")
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "address": forms.Textarea(attrs={"rows": 2}), "service_areas": forms.CheckboxSelectMultiple()}


class GroceryProductForm(forms.ModelForm):
    class Meta:
        model = GroceryProduct
        fields = ("category", "name", "brand", "image", "unit", "mrp", "price", "stock", "is_active", "is_perishable")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("price") and cleaned.get("mrp") and cleaned["price"] > cleaned["mrp"]:
            self.add_error("price", "Selling price cannot exceed MRP.")
        return cleaned


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
