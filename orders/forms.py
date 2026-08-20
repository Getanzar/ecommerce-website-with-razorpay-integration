# orders/forms.py

from django import forms


class CheckoutForm(forms.Form):

    PAYMENT_CHOICES = [
        ("online", "💳 Pay Online (UPI / Cards / Net Banking)"),
        ("cod", "💵 Cash on Delivery"),
    ]

    full_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your full name",
            "autocomplete": "name",
        })
    )

    phone = forms.CharField(
        max_length=15,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "10-digit mobile number",
            "autocomplete": "tel",
        })
    )

    address = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "House No., Street, Area",
            "autocomplete": "street-address",
        })
    )

    city = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "City",
            "autocomplete": "address-level2",
        })
    )

    state = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "State",
            "autocomplete": "address-level1",
        })
    )

    pincode = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "6-digit Pincode",
            "maxlength": "6",
            "inputmode": "numeric",
            "autocomplete": "postal-code",
        })
    )

    payment_method = forms.ChoiceField(
        choices=PAYMENT_CHOICES,
        initial="online",
        widget=forms.RadioSelect(attrs={
            "class": "form-check-input",
        })
    )

    # ---------- Validation ----------

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()

        # Remove spaces and +
        phone = phone.replace(" ", "").replace("+", "")

        # Remove India country code if present
        if phone.startswith("91") and len(phone) == 12:
            phone = phone[2:]

        if not phone.isdigit():
            raise forms.ValidationError("Invalid phone number.")

        if len(phone) != 10:
            raise forms.ValidationError("Enter a valid 10-digit mobile number.")

        return phone

    def clean_pincode(self):
        pincode = self.cleaned_data["pincode"].strip()

        if not pincode.isdigit():
            raise forms.ValidationError("Pincode must contain only digits.")

        if len(pincode) != 6:
            raise forms.ValidationError("Enter a valid 6-digit pincode.")

        return pincode