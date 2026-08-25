from django import forms
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone

from .models import DeliveryAgentProfile


class RequiredGPSMixin:
    """Require a browser-captured, reasonably accurate GPS fix."""
    gps_field_names = ("latitude", "longitude", "gps_accuracy_meters")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.gps_field_names:
            self.fields[name].required = True
            self.fields[name].widget = forms.HiddenInput()
        self.fields["gps_captured_at"] = forms.DateTimeField(required=True, widget=forms.HiddenInput())

    def clean(self):
        cleaned = super().clean()
        latitude_name, longitude_name, accuracy_name = self.gps_field_names
        latitude = cleaned.get(latitude_name)
        longitude = cleaned.get(longitude_name)
        accuracy = cleaned.get(accuracy_name)
        captured_at = cleaned.get("gps_captured_at")
        if latitude is None or longitude is None or accuracy is None:
            self.add_error(latitude_name, "Capture your current GPS location before continuing.")
            return cleaned
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise forms.ValidationError("The captured GPS coordinates are invalid.")
        if accuracy > 500:
            raise forms.ValidationError("GPS accuracy must be within 500 metres. Move outdoors and capture again.")
        if captured_at is None or abs((timezone.now() - captured_at).total_seconds()) > 300:
            raise forms.ValidationError("Your GPS location has expired. Capture it again before continuing.")
        return cleaned


class DeliveryAgentRegistrationForm(forms.ModelForm):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = DeliveryAgentProfile
        fields = (
            "full_name", "phone", "address", "city", "state", "pincode",
            "vehicle_type", "vehicle_number", "aadhaar_last4",
            "driving_license_number", "id_document", "driving_license_image",
            "bank_account_holder", "bank_account_last4", "bank_ifsc_code",
        )
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}

    def clean_username(self):
        value = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=value).exists():
            raise forms.ValidationError("That username is already in use.")
        return value

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError("That email is already registered.")
        return value

    def clean_aadhaar_last4(self):
        value = self.cleaned_data["aadhaar_last4"].strip()
        if len(value) != 4 or not value.isdigit():
            raise forms.ValidationError("Enter the last 4 digits of Aadhaar.")
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") != cleaned.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        vehicle = cleaned.get("vehicle_type")
        if vehicle in {"motorcycle", "ev"} and not cleaned.get("driving_license_number"):
            self.add_error("driving_license_number", "A driving licence is required for this vehicle.")
        return cleaned


class DeliveryOTPForm(forms.Form):
    otp = forms.CharField(
        min_length=6, max_length=6,
        validators=[RegexValidator(r"^\d{6}$", "Enter the 6-digit delivery OTP.")],
    )


class DeliveryAgentPayoutSetupForm(forms.Form):
    bank_account_holder = forms.CharField(max_length=120)
    bank_account_number = forms.CharField(min_length=9, max_length=18, widget=forms.PasswordInput(attrs={"autocomplete": "off", "inputmode": "numeric"}))
    bank_ifsc_code = forms.CharField(min_length=11, max_length=11)

    def clean_bank_account_number(self):
        value = self.cleaned_data["bank_account_number"].strip()
        if not value.isdigit():
            raise forms.ValidationError("Bank account number must contain only digits.")
        return value

    def clean_bank_ifsc_code(self):
        return self.cleaned_data["bank_ifsc_code"].strip().upper()
