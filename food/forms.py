from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import FoodOrder, MenuItem, MenuItemOption, MenuSection, Restaurant
from delivery.forms import RequiredGPSMixin


class RestaurantForm(RequiredGPSMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not field.widget.is_hidden and not isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                field.widget.attrs["class"] = "form-control"

    def clean_image(self):
        from accounts.seller_profile import validate_store_image
        return validate_store_image(self.cleaned_data.get("image"))

    class Meta:
        model = Restaurant
        fields = ("name", "description", "image", "cuisine", "pincode", "latitude", "longitude", "gps_accuracy_meters", "preparation_minutes", "minimum_order", "delivery_fee", "accepts_orders", "service_areas")
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "service_areas": forms.CheckboxSelectMultiple()}


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ("section", "name", "description", "image", "food_type", "is_available", "accepts_notes")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, restaurant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if restaurant:
            self.fields["section"].queryset = restaurant.sections.all()


class MenuOptionForm(forms.ModelForm):
    price = forms.DecimalField(max_digits=8, decimal_places=2, min_value=0.01)

    class Meta:
        model = MenuItemOption
        fields = ("name", "price", "is_available")


class BaseMenuOptionFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if not any(
            form.cleaned_data.get("price") is not None
            and not form.cleaned_data.get("DELETE", False)
            for form in self.forms
        ):
            raise forms.ValidationError("Add at least one size and price.")


MenuOptionFormSet = inlineformset_factory(
    MenuItem, MenuItemOption, form=MenuOptionForm, formset=BaseMenuOptionFormSet,
    fields=("name", "price", "is_available"), extra=3, can_delete=True,
    widgets={"price": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"})},
)


class MenuSectionForm(forms.ModelForm):
    class Meta:
        model = MenuSection
        fields = ("name", "display_order")


class FoodCheckoutForm(RequiredGPSMixin, forms.ModelForm):
    class Meta:
        model = FoodOrder
        fields = ("full_name", "phone", "address", "city", "state", "pincode", "latitude", "longitude", "gps_accuracy_meters", "include_cutlery", "delivery_note", "payment_method")
        widgets = {"address": forms.Textarea(attrs={"rows": 3}), "delivery_note": forms.Textarea(attrs={"rows": 2, "placeholder": "Landmark or delivery instructions"})}

    def clean_pincode(self):
        value = self.cleaned_data["pincode"].strip()
        if not value.isdigit() or len(value) != 6:
            raise forms.ValidationError("Enter a valid 6-digit pincode.")
        return value
