from django import forms
from .models import ProductReview


class ProductReviewForm(forms.ModelForm):

    class Meta:
        model = ProductReview

        fields = [
            "rating",
            "title",
            "review",
        ]

        widgets = {
            "rating": forms.Select(
                choices=[
                    (5, "★★★★★"),
                    (4, "★★★★☆"),
                    (3, "★★★☆☆"),
                    (2, "★★☆☆☆"),
                    (1, "★☆☆☆☆"),
                ],
                attrs={
                    "class": "form-select",
                },
            ),

            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Review title",
                },
            ),

            "review": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Write your review...",
                },
            ),
        }