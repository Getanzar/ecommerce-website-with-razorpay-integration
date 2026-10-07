from django import forms
from django.core.validators import RegexValidator
from django.utils import timezone

from delivery.forms import RequiredGPSMixin
from .models import SellerProfile


def validate_store_image(image):
    if image and getattr(image, "size", 0) > 8 * 1024 * 1024:
        raise forms.ValidationError("Choose an image smaller than 8 MB.")
    return image


class SellerProfileForm(RequiredGPSMixin, forms.ModelForm):
    business_pincode = forms.CharField(validators=[RegexValidator(r"^\d{6}$", "Enter a 6-digit pincode.")])
    business_phone = forms.CharField(max_length=20, validators=[RegexValidator(r"^\+?[0-9]{10,15}$", "Enter a valid contact number.")])

    class Meta:
        model = SellerProfile
        fields = ("store_name", "description", "logo", "cover_image", "business_phone", "business_address", "business_pincode", "business_latitude", "business_longitude", "business_gps_accuracy_meters")
        labels = {"store_name": "Business name", "logo": "Profile photo / logo", "cover_image": "Cover photo", "business_address": "Pickup address", "business_pincode": "Pickup pincode", "description": "About your business"}
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "business_address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        self.gps_field_names = ("business_latitude", "business_longitude", "business_gps_accuracy_meters")
        super().__init__(*args, **kwargs)
        self.fields["business_address"].required = True
        for field in self.fields.values():
            if not field.widget.is_hidden:
                field.widget.attrs["class"] = "form-control"

    def clean_logo(self):
        return validate_store_image(self.cleaned_data.get("logo"))

    def clean_cover_image(self):
        return validate_store_image(self.cleaned_data.get("cover_image"))

    def save(self, commit=True):
        seller = super().save(commit=False)
        seller.business_gps_verified_at = timezone.now()
        if commit:
            seller.save()
            sync_profile_location(seller)
        return seller


def sync_profile_location(seller):
    """Keep the active service store's pickup consistent with seller coverage."""
    from food.models import Restaurant
    from groceries.models import GroceryStore
    location = {"pincode": seller.business_pincode, "latitude": seller.business_latitude,
                "longitude": seller.business_longitude, "gps_accuracy_meters": seller.business_gps_accuracy_meters,
                "gps_verified_at": seller.business_gps_verified_at}
    if seller.business_segment == "food":
        Restaurant.objects.filter(seller=seller).update(**location)
    elif seller.business_segment == "grocery":
        GroceryStore.objects.filter(seller=seller).update(**location, address=seller.business_address, phone=seller.business_phone)


def sync_store_location(store):
    seller = store.seller
    seller.business_pincode = store.pincode
    seller.business_latitude = store.latitude
    seller.business_longitude = store.longitude
    seller.business_gps_accuracy_meters = store.gps_accuracy_meters
    seller.business_gps_verified_at = timezone.now()
    fields = ["business_pincode", "business_latitude", "business_longitude", "business_gps_accuracy_meters", "business_gps_verified_at", "updated_at"]
    if hasattr(store, "address"):
        seller.business_address, seller.business_phone = store.address, store.phone
        fields += ["business_address", "business_phone"]
    seller.save(update_fields=fields)
