import re

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import SellerProfile, UserProfile
from .identity import normalize_phone, duplicate_identifiers


class SignUpForm(forms.Form):

    first_name = forms.CharField(
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "First Name",
                "autocomplete": "given-name",
            }
        ),
    )

    last_name = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Last Name (Optional)",
                "autocomplete": "family-name",
            }
        ),
    )

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Username",
                "autocomplete": "username",
            }
        ),
    )

    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Email Address",
                "autocomplete": "email",
            }
        ),
    )

    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "10-digit Mobile Number",
                "autocomplete": "tel",
                "maxlength": "20",
                "inputmode": "numeric",
            }
        ),
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Password",
                "autocomplete": "new-password",
            }
        ),
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Confirm Password",
                "autocomplete": "new-password",
            }
        ),
    )

    terms = forms.BooleanField(
        error_messages={
            "required": "You must accept the Terms & Conditions."
        },
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
            }
        ),
    )

    def clean_first_name(self):
        first_name = self.cleaned_data["first_name"].strip()

        if len(first_name) < 2:
            raise ValidationError(
                "First name must contain at least 2 characters."
            )

        return first_name.title()

    def clean_last_name(self):
        return self.cleaned_data["last_name"].strip().title()

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()

        if len(username) < 4:
            raise ValidationError(
                "Username must be at least 4 characters."
            )

        error = duplicate_identifiers(username, "", "").get("username")
        if error:
            raise ValidationError(error, code="existing_account")

        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        error = duplicate_identifiers("", email, "").get("email")
        if error:
            raise ValidationError(error, code="existing_account")

        return email

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])

        if not re.fullmatch(r"[6-9]\d{9}", phone):
            raise ValidationError(
                "Enter a valid 10-digit Indian mobile number."
            )

        error = duplicate_identifiers("", "", phone).get("phone")
        if error:
            raise ValidationError(error, code="existing_account")

        return phone

    def clean_password1(self):
        password = self.cleaned_data["password1"]

        validate_password(password)

        return password

    def clean(self):
        cleaned_data = super().clean()

        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error(
                "password2",
                "Passwords do not match."
            )

        return cleaned_data

    @property
    def has_existing_account(self):
        return any(error.code == "existing_account" for errors in self.errors.as_data().values() for error in errors)

    def save(self):
        if not self.is_valid():
            raise ValueError("A user cannot be created from an invalid signup form.")

        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            is_active=False,  # User cannot login until email is verified
        )

        profile, created = UserProfile.objects.get_or_create(user=user)

        profile.phone = self.cleaned_data["phone"]
        profile.phone_verified = False
        profile.email_verified = False
        profile.save()

        return user


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
    pan_number = forms.CharField(max_length=10, min_length=10, label="PAN", widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "off"}), help_text="Needed to match your GST-portal enrolment. Only the last four characters are retained.")
    gst_enrolment_number = forms.CharField(max_length=20, min_length=10, label="GST-portal enrolment number", widget=forms.TextInput(attrs={"class": "form-control"}), help_text="The enrolment number for an unregistered e-commerce supplier, not a GSTIN.")
    aadhaar_consent = forms.BooleanField(label="I consent to Aadhaar offline identity verification for my seller application.", widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    eligibility_declaration = forms.BooleanField(label="I am not GST registered, meet the applicable turnover limit, and will sell only within my registered state through this enrolment.", widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("gstin")
        self.fields["business_segment"].widget = forms.HiddenInput()
        self.fields["business_segment"].initial = "shop"
        self.fields["legal_business_name"].label = "Your legal name"
        self.fields["business_category"].widget.attrs["placeholder"] = "e.g. Handmade items, Clothing, Home decor"
        self.fields["aadhaar_last4"].label = "Last four digits of Aadhaar"
        self.fields["bank_ifsc_code"].label = "Bank IFSC code"
        self.fields["aadhaar_last4"].help_text = "Enter only the last four digits. Our team will verify your Aadhaar Secure QR during identity review. Do not upload or send your full Aadhaar number."
        self.instance.registration_type = "small"
        self.instance.business_segment = "shop"
        self.instance.gstin = ""

    def clean_business_segment(self):
        if self.cleaned_data["business_segment"] != "shop":
            raise ValidationError("This registration is for merchandise only.")
        return "shop"

    def clean_pan_number(self):
        value = self.cleaned_data["pan_number"].strip().upper()
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", value):
            raise ValidationError("Enter a valid PAN.")
        return value

    def clean_business_phone(self):
        value = self.cleaned_data["business_phone"].strip()
        if not re.fullmatch(r"(?:\+91)?[6-9]\d{9}", value):
            raise ValidationError("Enter a valid Indian mobile number for identity review.")
        return value

    def clean_gst_enrolment_number(self):
        value = self.cleaned_data["gst_enrolment_number"].strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{10,20}", value):
            raise ValidationError("Enter the enrolment number issued by the GST portal.")
        return value

    def save(self, commit=True):
        from django.utils import timezone
        seller = super().save(commit=False)
        seller.registration_type = "small"
        seller.business_segment = "shop"
        seller.gstin = ""
        seller.pan_last4 = self.cleaned_data["pan_number"][-4:]
        seller.gst_enrolment_number = self.cleaned_data["gst_enrolment_number"]
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
    identity_checked = forms.BooleanField(label="I verified the seller's identity against their Aadhaar Secure QR using official UIDAI offline tools and confirmed their consent.")
    enrolment_checked = forms.BooleanField(label="I verified GST-portal enrolment, PAN match, registered state and applicable turnover eligibility.")
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
