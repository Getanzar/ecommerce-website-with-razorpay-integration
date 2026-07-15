import re

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import UserProfile


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