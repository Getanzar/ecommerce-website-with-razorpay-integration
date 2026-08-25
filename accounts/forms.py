import re

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import SellerProfile, UserProfile


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
        max_length=10,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "10-digit Mobile Number",
                "autocomplete": "tel",
                "maxlength": "10",
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

        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(
                "This username is already taken."
            )

        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "An account with this email already exists."
            )

        return email

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()

        if not re.fullmatch(r"[6-9]\d{9}", phone):
            raise ValidationError(
                "Enter a valid 10-digit Indian mobile number."
            )

        if UserProfile.objects.filter(phone=phone).exists():
            raise ValidationError(
                "This phone number is already registered."
            )

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
