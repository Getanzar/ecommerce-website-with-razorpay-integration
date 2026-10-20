import re

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import SellerProfile, UserProfile
from .identity import normalize_phone, duplicate_identifiers


class SignUpForm(forms.Form):
    email = forms.EmailField(max_length=254, widget=forms.EmailInput(attrs={"class": "form-control form-control-lg", "placeholder": "you@example.com", "autocomplete": "email"}))
    password1 = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"class": "form-control form-control-lg", "autocomplete": "new-password", "placeholder": "Create a password"}))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        error = duplicate_identifiers("", email, "").get("email")
        if error:
            raise ValidationError(error, code="existing_account")
        return email

    def clean(self):
        data = super().clean()
        if data.get("password1"):
            validate_password(data["password1"], User(email=data.get("email", "")))
        return data

    @property
    def has_existing_account(self):
        return any(error.code == "existing_account" for errors in self.errors.as_data().values() for error in errors)

    def save(self):
        if not self.is_valid():
            raise ValueError("A user cannot be created from an invalid signup form.")
        from .identity import generate_username
        return User.objects.create_user(username=generate_username(), email=self.cleaned_data["email"], password=self.cleaned_data["password1"], is_active=False)


from django.contrib.auth.forms import AuthenticationForm


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="Email or username", max_length=254, widget=forms.TextInput(attrs={"class": "form-control form-control-lg", "autocomplete": "username", "placeholder": "Email or username", "autofocus": True}))
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"class": "form-control form-control-lg", "autocomplete": "current-password"}))


class CustomerProfileForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    username = forms.CharField(max_length=150)
    email = forms.EmailField(max_length=254)
    phone = forms.CharField(max_length=20, required=False)
    gender = forms.ChoiceField(choices=[("", "Select gender"), *UserProfile.GENDER_CHOICES], required=False)
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    profile_picture = forms.ImageField(required=False)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        profile, _ = UserProfile.objects.get_or_create(user=user)
        kwargs.setdefault("initial", {**{key: getattr(user, key) for key in ("first_name", "last_name", "username", "email")}, **{key: getattr(profile, key) for key in ("phone", "gender", "date_of_birth")}})
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_username(self):
        return User._meta.get_field("username").clean(self.cleaned_data["username"].strip(), self.user)

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get("phone", ""))
        if phone and not re.fullmatch(r"[6-9][0-9]{9}", phone):
            raise ValidationError("Enter a valid 10-digit Indian mobile number.")
        return phone

    def clean_profile_picture(self):
        picture = self.cleaned_data.get("profile_picture")
        if picture and picture.size > 5 * 1024 * 1024:
            raise ValidationError("Choose a profile picture smaller than 5 MB.")
        return picture

    def clean(self):
        data = super().clean()
        for field, error in duplicate_identifiers(data.get("username", ""), data.get("email", ""), data.get("phone", ""), exclude_user_id=self.user.pk).items():
            self.add_error(field, error)
        return data


from delivery.forms import RequiredGPSMixin


class SellerApplicationForm(RequiredGPSMixin, forms.ModelForm):
    bank_account_number = forms.CharField(
        min_length=9,
        max_length=18,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "off",
                "inputmode": "numeric",
            }
        ),
        help_text="Used only to verify your details. We retain only the last four digits.",
    )

    class Meta:
        model = SellerProfile
        fields = (
            "store_name",
            "legal_business_name",
            "business_category",
            "business_segment",
            "business_phone",
            "business_address",
            "business_pincode",
            "business_latitude",
            "business_longitude",
            "business_gps_accuracy_meters",
            "gstin",
            "aadhaar_last4",
            "bank_account_holder",
            "bank_ifsc_code",
        )
        widgets = {
            "store_name": forms.TextInput(attrs={"class": "form-control"}),
            "legal_business_name": forms.TextInput(attrs={"class": "form-control"}),
            "business_category": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. Clothing, Food, Home decor"}
            ),
            "business_segment": forms.Select(attrs={"class": "form-select"}),
            "business_phone": forms.TextInput(attrs={"class": "form-control"}),
            "business_address": forms.Textarea(
                attrs={"class": "form-control", "rows": 4}
            ),
            "business_pincode": forms.TextInput(attrs={"class": "form-control", "maxlength": "6", "inputmode": "numeric"}),
            "gstin": forms.TextInput(
                attrs={"class": "form-control", "style": "text-transform:uppercase"}
            ),
            "aadhaar_last4": forms.TextInput(
                attrs={"class": "form-control", "inputmode": "numeric", "maxlength": "4"}
            ),
            "bank_account_holder": forms.TextInput(attrs={"class": "form-control"}),
            "bank_ifsc_code": forms.TextInput(
                attrs={"class": "form-control", "style": "text-transform:uppercase"}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.gps_field_names = ("business_latitude", "business_longitude", "business_gps_accuracy_meters")
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True
            field.widget.attrs["required"] = True
            field.widget.attrs["aria-required"] = "true"

    def clean_gstin(self):
        gstin = self.cleaned_data["gstin"].strip().upper()
        if not re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]", gstin):
            raise ValidationError("Enter a valid 15-character GSTIN.")
        return gstin

    def clean_business_pincode(self):
        value = self.cleaned_data["business_pincode"].strip()
        if len(value) != 6 or not value.isdigit():
            raise ValidationError("Enter a valid 6-digit business pincode.")
        return value

    def clean_aadhaar_last4(self):
        aadhaar_last4 = self.cleaned_data["aadhaar_last4"].strip()
        if not re.fullmatch(r"\d{4}", aadhaar_last4):
            raise ValidationError("Enter the last four digits of Aadhaar.")
        return aadhaar_last4

    def clean_bank_account_number(self):
        account_number = self.cleaned_data["bank_account_number"].replace(" ", "")
        if not account_number.isdigit():
            raise ValidationError("Account number must contain digits only.")
        return account_number

    def clean_bank_ifsc_code(self):
        ifsc_code = self.cleaned_data["bank_ifsc_code"].strip().upper()
        if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", ifsc_code):
            raise ValidationError("Enter a valid 11-character IFSC code.")
        return ifsc_code

    def save(self, commit=True):
        seller = super().save(commit=False)
        seller.bank_account_last4 = self.cleaned_data["bank_account_number"][-4:]
        if commit:
            seller.save()
        return seller


class SmallSellerApplicationForm(SellerApplicationForm):
    aadhaar_image = forms.ImageField(label="Masked Aadhaar photo", widget=forms.FileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp"}), help_text="Upload a clear JPG, PNG or WebP up to 8 MB. Hide the first eight Aadhaar digits; keep your name, photo, last four digits and Secure QR visible. Only authorised admins can view this image.")

    class Meta(SellerApplicationForm.Meta):
        fields = (*SellerApplicationForm.Meta.fields, "aadhaar_image")

    def clean_aadhaar_image(self):
        image = self.cleaned_data.get("aadhaar_image")
        if image and hasattr(image, "image"):
            if image.size > 8 * 1024 * 1024:
                raise ValidationError("Aadhaar image must be 8 MB or smaller.")
            if image.image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValidationError("Upload a JPG, PNG or WebP image.")
        return image

    aadhaar_consent = forms.BooleanField(label="I consent to uploading and storing my masked Aadhaar photo for authorised admin review of my seller application.", widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    eligibility_declaration = forms.BooleanField(label="I am a small seller without GST registration, meet the applicable turnover limit, and will sell only within my approved local selling area.", widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def __init__(self, *args, **kwargs):
        self.segment = kwargs.pop("segment", "shop")
        if self.segment not in dict(SellerProfile.BUSINESS_SEGMENTS):
            raise ValueError("Unknown small seller segment.")
        super().__init__(*args, **kwargs)
        self.fields.pop("gstin")
        self.fields["business_segment"].widget = forms.HiddenInput()
        self.fields["business_segment"].initial = self.segment
        self.fields["legal_business_name"].label = "Your legal name"
        self.fields["business_category"].widget.attrs["placeholder"] = "e.g. Handmade items, Clothing, Home decor"
        self.fields["aadhaar_last4"].label = "Last four digits of Aadhaar"
        self.fields["bank_ifsc_code"].label = "Bank IFSC code"
        self.fields["aadhaar_last4"].help_text = "Enter only the last four digits. These digits must match your masked Aadhaar photo. Do not enter your full Aadhaar number."
        self.instance.registration_type = "small"
        self.instance.business_segment = self.segment
        if self.segment != "shop":
            self.fields["business_category"].widget.attrs["placeholder"] = (
                "e.g. Home kitchen, Snacks, Restaurant" if self.segment == "food"
                else "e.g. Kirana, Fresh produce, Daily essentials"
            )
        self.instance.gstin = ""

    def clean_business_segment(self):
        if self.cleaned_data["business_segment"] != self.segment:
            raise ValidationError("Select the registration flow for your selling segment.")
        return self.segment

    def clean_business_phone(self):
        value = self.cleaned_data["business_phone"].strip()
        if not re.fullmatch(r"(?:\+91)?[6-9]\d{9}", value):
            raise ValidationError("Enter a valid Indian mobile number for identity review.")
        return value

    def save(self, commit=True):
        from django.utils import timezone
        seller = super().save(commit=False)
        seller.registration_type = "small"
        seller.business_segment = self.segment
        seller.gstin = ""
        seller.small_seller_declaration = True
        seller.aadhaar_consent_at = timezone.now()
        seller.identity_status = "pending"
        seller.identity_verified_at = None
        seller.identity_verified_by = None
        seller.identity_review_reference = ""
        seller.identity_review_note = ""
        seller.payouts_enabled = False
        seller.razorpay_contact_id = ""
        seller.razorpay_fund_account_id = ""
        if commit:
            seller.save()
        return seller


class SmallSellerReviewForm(forms.Form):
    identity_checked = forms.BooleanField(label="I reviewed the uploaded masked Aadhaar photo, matched the name and last four digits to this application, and confirmed the seller consented.")
    eligibility_checked = forms.BooleanField(label="I reviewed the seller's business details, approved selling area and small-seller declaration.")
    reference = forms.CharField(max_length=100, label="Review reference", help_text="Use an internal review reference, never an Aadhaar number.")

    def clean_reference(self):
        value = self.cleaned_data["reference"].strip()
        if re.search(r"\d{12}", re.sub(r"[\s-]", "", value)):
            raise ValidationError("Do not include an Aadhaar number in the review reference.")
        return value


class SellerPayoutSetupForm(forms.Form):
    bank_account_holder = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "name"}),
    )
    bank_account_number = forms.CharField(
        min_length=9, max_length=18,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "off", "inputmode": "numeric"}),
        help_text="Sent securely to RazorpayX. ZIYAMART stores only the last four digits.",
    )
    confirm_bank_account_number = forms.CharField(
        min_length=9, max_length=18,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "off", "inputmode": "numeric"}),
    )
    bank_ifsc_code = forms.CharField(
        min_length=11, max_length=11,
        widget=forms.TextInput(attrs={"class": "form-control", "style": "text-transform:uppercase"}),
    )

    def clean_bank_account_number(self):
        value = self.cleaned_data["bank_account_number"].replace(" ", "")
        if not value.isdigit():
            raise ValidationError("Account number must contain digits only.")
        return value

    def clean_bank_ifsc_code(self):
        value = self.cleaned_data["bank_ifsc_code"].strip().upper()
        if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", value):
            raise ValidationError("Enter a valid 11-character IFSC code.")
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("bank_account_number") != cleaned.get("confirm_bank_account_number", "").replace(" ", ""):
            self.add_error("confirm_bank_account_number", "Account numbers do not match.")
        return cleaned


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "autocomplete": "email",
                "placeholder": "Email address",
            }
        )
    )


class SetPasswordWithOTPForm(forms.Form):
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"}
        )
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"}
        )
    )

    def clean_new_password1(self):
        password = self.cleaned_data["new_password1"]
        validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("new_password1")
            and cleaned_data.get("new_password1") != cleaned_data.get("new_password2")
        ):
            self.add_error("new_password2", "Passwords do not match.")
        return cleaned_data
