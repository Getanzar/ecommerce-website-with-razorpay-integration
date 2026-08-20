from django import forms
from django.forms import inlineformset_factory

from .models import FoodOrder, MenuItem, MenuItemOption, MenuSection, Restaurant


class RestaurantForm(forms.ModelForm):
    class Meta:
        model = Restaurant
        fields = ("name", "description", "image", "cuisine", "preparation_minutes", "minimum_order", "delivery_fee", "accepts_orders", "service_areas")
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


MenuOptionFormSet = inlineformset_factory(
    MenuItem, MenuItemOption, fields=("name", "price", "is_available"), extra=3, can_delete=True,
    widgets={"price": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"})},
)


class MenuSectionForm(forms.ModelForm):
    class Meta:
        model = MenuSection
        fields = ("name", "display_order")


class FoodCheckoutForm(forms.ModelForm):
    class Meta:
        model = FoodOrder
        fields = ("full_name", "phone", "address", "city", "state", "pincode", "include_cutlery", "delivery_note", "payment_method")
        widgets = {"address": forms.Textarea(attrs={"rows": 3}), "delivery_note": forms.Textarea(attrs={"rows": 2, "placeholder": "Landmark or delivery instructions"})}

    def clean_pincode(self):
        value = self.cleaned_data["pincode"].strip()
        if not value.isdigit() or len(value) != 6:
            raise forms.ValidationError("Enter a valid 6-digit pincode.")
        return value
