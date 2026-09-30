"""Native form contracts built from the same validators as the web workspace."""
from django import forms
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework import serializers
from rest_framework.response import Response

from accounts.forms import SellerApplicationForm, SellerPayoutSetupForm
from accounts.models import SellerProfile
from dashboard.forms import SellerProductEditForm, SellerProductForm
from delivery.forms import DeliveryAgentRegistrationForm
from delivery.models import DeliveryAgentProfile
from products.models import (
    Category,
    SubCategory,
    Product,
    ProductColor,
    ProductImage,
    ProductVariant,
)
from .partners import PartnerView, SellerKindView, seller_for
from food.forms import RestaurantForm, MenuItemForm
from food.models import Restaurant, MenuItem, MenuSection, MenuItemOption
from groceries.forms import GroceryStoreForm, GroceryProductForm
from groceries.models import GroceryStore, GroceryProduct


class RiderApplicationForm(DeliveryAgentRegistrationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("username", "email", "password", "confirm_password", "bank_account_holder", "bank_account_last4", "bank_ifsc_code"):
            self.fields.pop(name, None)


class MobileProductForm(SellerProductForm):
    color_name = forms.CharField(max_length=50, initial="Standard")
    size = forms.CharField(max_length=30, initial="Free Size")
    opening_stock = forms.IntegerField(min_value=0, max_value=1000000)
    variants = forms.JSONField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound and "variants" in self.data:
            for name in ("color_name", "size", "opening_stock"):
                self.fields[name].required = False

    def clean_variants(self):
        rows = self.cleaned_data.get("variants")
        if "variants" not in self.data:
            return None  # Older clients still submit one color/size.
        if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            raise forms.ValidationError("Add between 1 and 100 color/size variants.")
        cleaned, seen = [], set()
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                raise forms.ValidationError(f"Variant {index}: invalid variant.")
            try:
                color = serializers.CharField(max_length=50).run_validation(row.get("color"))
                size = serializers.CharField(max_length=30).run_validation(row.get("size"))
                stock = serializers.IntegerField(min_value=0, max_value=1000000).run_validation(row.get("stock"))
            except ValidationError as exc:
                raise forms.ValidationError(f"Variant {index}: {exc.detail}") from exc
            key = (color.casefold(), size.casefold())
            if key in seen:
                raise forms.ValidationError(f"Variant {index}: {color} / {size} is repeated. Use one stock quantity per color and size.")
            seen.add(key)
            cleaned.append({"color": color, "size": size, "stock": stock})
        return cleaned


def schema(form):
    fields = []
    for name, field in form.fields.items():
        value = form.initial.get(name, field.initial)
        is_image = isinstance(field, forms.ImageField)
        kind = ("image" if is_image else "hidden" if field.widget.is_hidden else
                "multiple" if isinstance(field, forms.ModelMultipleChoiceField) else
                "choice" if isinstance(field, forms.ChoiceField) else
                "boolean" if isinstance(field, forms.BooleanField) else
                "password" if isinstance(field.widget, forms.PasswordInput) else
                "number" if isinstance(field, (forms.IntegerField, forms.DecimalField)) else
                "multiline" if isinstance(field.widget, forms.Textarea) else "text")
        fields.append({"name": name, "label": field.label or name.replace("_", " ").capitalize(),
                       "required": field.required, "type": kind,
                       "value": ",".join(str(v.pk if hasattr(v, "pk") else v) for v in value) if kind == "multiple" and value is not None else "" if value is None or is_image or kind == "password" else str(value),
                       "choices": [[str(key), str(title)] for key, title in field.choices] if hasattr(field, "choices") else [],
                       "help": str(field.help_text)})
    return {"fields": fields}


def validate(form):
    for uploaded in form.files.values():
        if uploaded.size > 8 * 1024 * 1024:
            raise ValidationError("Each image must be smaller than 8 MB.")
    if not form.is_valid():
        raise ValidationError({key: [str(error) for error in errors] for key, errors in form.errors.items()})


class ApplicationView(PartnerView):
    def form(self, request, role, submitted=False):
        model, form_class = {"seller": (SellerProfile, SellerApplicationForm), "rider": (DeliveryAgentProfile, RiderApplicationForm)}.get(role, (None, None))
        if model is None:
            raise ValidationError("Unknown partner role.")
        if model.objects.filter(user=request.user).exists():
            raise PermissionDenied("An application already exists. Contact support for changes.")
        return form_class(request.data if submitted else None, request.FILES if submitted else None)

    def get(self, request, role):
        return Response(schema(self.form(request, role)))

    @transaction.atomic
    def post(self, request, role):
        User.objects.select_for_update().get(pk=request.user.pk)
        form = self.form(request, role, True)
        validate(form)
        profile = form.save(commit=False)
        profile.user = request.user
        profile.status = "pending"
        profile.payouts_enabled = False
        if role == "seller":
            profile.business_gps_verified_at = timezone.now()
        profile.save()
        # Do not initiate provider calls during application submission. Bank setup
        # is a separate explicit action and approval never enables payouts itself.
        return Response({"message": "Application submitted for marketplace review. Complete payout setup separately.", "status": profile.status}, status=201)


class PayoutSetupView(PartnerView):
    def profile(self, request, role):
        model = {"seller": SellerProfile, "rider": DeliveryAgentProfile}.get(role)
        if not model:
            raise ValidationError("Unknown role.")
        return get_object_or_404(model, user=request.user)

    def get(self, request, role):
        profile = self.profile(request, role)
        return Response(schema(SellerPayoutSetupForm(initial={"bank_account_holder": profile.bank_account_holder, "bank_ifsc_code": profile.bank_ifsc_code})))

    @transaction.atomic
    def post(self, request, role):
        profile = self.profile(request, role)
        profile = type(profile).objects.select_for_update().get(pk=profile.pk)
        if profile.status in {"suspended", "rejected"}:
            raise PermissionDenied("Contact marketplace support before changing payout details.")
        form = SellerPayoutSetupForm(request.data)
        validate(form)
        profile.bank_account_holder = form.cleaned_data["bank_account_holder"]
        profile.bank_ifsc_code = form.cleaned_data["bank_ifsc_code"]
        profile.bank_account_last4 = form.cleaned_data["bank_account_number"][-4:]
        from accounts.payouts import provision_seller_payout_account, PayoutOnboardingError
        from delivery.payouts import provision_agent_payout_account, AgentPayoutError
        try:
            (provision_seller_payout_account if role == "seller" else provision_agent_payout_account)(profile, form.cleaned_data["bank_account_number"])
        except (PayoutOnboardingError, AgentPayoutError):
            raise ValidationError("Payout provider could not verify these details. No local bank changes were saved. Try again or contact support.")
        profile.payouts_enabled = False
        profile.save(update_fields=["bank_account_holder", "bank_ifsc_code", "bank_account_last4", "payouts_enabled", "updated_at"])
        return Response({"message": "Bank details submitted. Payouts require marketplace verification."})


class ProductFormView(SellerKindView):
    def form(self, request, pk=None, submitted=False):
        seller = seller_for(request.user)
        instance = get_object_or_404(Product, pk=pk, seller=seller) if pk else None
        cls = SellerProductEditForm if instance else MobileProductForm
        return cls(request.data if submitted else None, request.FILES if submitted else None, instance=instance)

    def get(self, request, pk=None):
        return Response(schema(self.form(request, pk)))

    @transaction.atomic
    def post(self, request, pk=None):
        seller = seller_for(request.user)
        if pk:
            get_object_or_404(Product.objects.select_for_update(), pk=pk, seller=seller)
        form = self.form(request, pk, True)
        validate(form)
        product = form.save(commit=False)
        product.seller = seller
        product.moderation_status = Product.MODERATION_PENDING
        product.is_active = False
        product.rejection_reason = ""
        product.save()
        if pk is None:
            variants = form.cleaned_data.get("variants") or [{"color": form.cleaned_data["color_name"], "size": form.cleaned_data["size"], "stock": form.cleaned_data["opening_stock"]}]
            colors = {}
            for variant in variants:
                key = variant["color"].casefold()
                if key not in colors:
                    colors[key] = ProductColor.objects.create(product=product, name=variant["color"])
                ProductVariant.objects.create(product=product, color=colors[key], size=variant["size"], stock=variant["stock"])
            ProductImage.objects.create(product=product, image=form.cleaned_data["back_image"])
        return Response({"message": "Product submitted for catalog review.", "id": product.pk}, status=200 if pk else 201)

class SellerCategoryView(SellerKindView):

    def get(self, request):
        """
        Return the complete merchandise category tree.

        Used by the mobile Seller Center so that:
        Category -> Subcategory
        selections can be filtered correctly.
        """
        seller_for(request.user)  # Approved sellers only

        categories = (
            Category.objects
            .prefetch_related("subcategories")
            .order_by("name")
        )

        results = []

        for category in categories:
            results.append({
                "id": category.pk,
                "name": category.name,
                "slug": category.slug,
                "subcategories": [
                    {
                        "id": subcategory.pk,
                        "name": subcategory.name,
                    }
                    for subcategory in category.subcategories.all().order_by("name")
                ],
            })

        return Response({
            "categories": results,
        })

    @transaction.atomic
    def post(self, request):
        seller_for(request.user)  # Ensures this is an approved seller

        name = str(request.data.get("name", "")).strip()
        parent_category_id = request.data.get("parent_category")

        if not name:
            raise ValidationError({
                "name": ["Category name is required."]
            })

        # ---------------------------------------------
        # CREATE SUBCATEGORY
        # ---------------------------------------------
        if parent_category_id:
            parent = get_object_or_404(
                Category,
                pk=parent_category_id,
            )

            existing = SubCategory.objects.filter(
                category=parent,
                name__iexact=name,
            ).first()

            if existing:
                return Response({
                    "message": "Subcategory already exists.",
                    "id": existing.pk,
                    "name": existing.name,
                    "category_id": parent.pk,
                    "type": "subcategory",
                })

            subcategory = SubCategory.objects.create(
                category=parent,
                name=name,
            )

            return Response({
                "message": "Subcategory created.",
                "id": subcategory.pk,
                "name": subcategory.name,
                "category_id": parent.pk,
                "type": "subcategory",
            }, status=201)

        # ---------------------------------------------
        # CREATE TOP-LEVEL CATEGORY
        # ---------------------------------------------
        existing = Category.objects.filter(
            name__iexact=name
        ).first()

        if existing:
            return Response({
                "message": "Category already exists.",
                "id": existing.pk,
                "name": existing.name,
                "type": "category",
            })

        category = Category.objects.create(
            name=name
        )

        return Response({
            "message": "Category created.",
            "id": category.pk,
            "name": category.name,
            "slug": category.slug,
            "type": "category",
        }, status=201)

class MobileMenuForm(MenuItemForm):
    section_name = forms.CharField(max_length=100, initial="Menu")
    option_name = forms.CharField(max_length=50, initial="Regular")
    option_price = forms.DecimalField(max_digits=8, decimal_places=2, min_value=0.01)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("section")
        if self.instance.pk:
            self.initial["section_name"] = self.instance.section.name
            self.fields.pop("option_name")
            self.fields.pop("option_price")


class StoreFormView(SellerKindView):
    def form(self, request, kind, submitted=False):
        seller = seller_for(request.user)
        model, cls = {"food": (Restaurant, RestaurantForm), "grocery": (GroceryStore, GroceryStoreForm)}.get(kind, (None, None))
        if not model:
            raise ValidationError("Unknown store type.")
        instance = model.objects.filter(seller=seller).first() or model(seller=seller)
        return cls(request.data if submitted else None, request.FILES if submitted else None, instance=instance)

    def get(self, request, kind):
        return Response(schema(self.form(request, kind)))

    @transaction.atomic
    def post(self, request, kind):
        SellerProfile.objects.select_for_update().get(pk=seller_for(request.user).pk)
        form = self.form(request, kind, True)
        validate(form)
        form.save()
        return Response({"message": "Store details saved."})


class ServiceProductFormView(SellerKindView):
    def form(self, request, kind, pk=None, submitted=False):
        seller = seller_for(request.user)
        data, files = (request.data, request.FILES) if submitted else (None, None)
        if kind == "food":
            restaurant = get_object_or_404(Restaurant, seller=seller)
            item = get_object_or_404(MenuItem, restaurant=restaurant, pk=pk) if pk else MenuItem(restaurant=restaurant)
            return MobileMenuForm(data, files, instance=item, restaurant=restaurant)
        if kind == "grocery":
            store = get_object_or_404(GroceryStore, seller=seller)
            if pk is None and (store.latitude is None or store.longitude is None):
                raise ValidationError("Set and verify your store location in Store settings before adding products. The saved location is used as the pickup point for every grocery delivery.")
            item = get_object_or_404(GroceryProduct, store=store, pk=pk) if pk else GroceryProduct(store=store)
            return GroceryProductForm(data, files, instance=item)
        raise ValidationError("Unknown catalog type.")

    def get(self, request, kind, pk=None):
        return Response(schema(self.form(request, kind, pk)))

    @transaction.atomic
    def post(self, request, kind, pk=None):
        SellerProfile.objects.select_for_update().get(pk=seller_for(request.user).pk)
        if pk:
            model = {"food": MenuItem, "grocery": GroceryProduct}.get(kind)
            if not model:
                raise ValidationError("Unknown catalog type.")
            # Ownership is validated before applying any field updates.
            from .partners import catalog
            get_object_or_404(catalog(seller_for(request.user), kind).select_for_update(), pk=pk)
        form = self.form(request, kind, pk, True)
        validate(form)
        item = form.save(commit=False)
        if kind == "food":
            item.section, _ = MenuSection.objects.get_or_create(restaurant=item.restaurant, name=form.cleaned_data["section_name"])
        item.save()
        if kind == "food" and pk is None:
            MenuItemOption.objects.create(item=item, name=form.cleaned_data["option_name"], price=form.cleaned_data["option_price"])
        return Response({"message": "Catalog item saved."})

class ProductColorFormView(SellerKindView):
    def get_product(self, request, pk):
        seller = seller_for(request.user)

        return get_object_or_404(
            Product,
            pk=pk,
            seller=seller,
        )

    def get(self, request, pk):
        product = self.get_product(request, pk)

        colors = product.colors.all().order_by(
            "display_order",
            "id",
        )

        return Response({
            "colors": [
                {
                    "id": color.pk,
                    "name": color.name,
                    "hex_code": color.hex_code,
                    "image": (
                        color.image.url
                        if color.image
                        else None
                    ),
                }
                for color in colors
            ]
        })

    @transaction.atomic
    def post(self, request, pk):
        product = self.get_product(request, pk)

        name = str(
            request.data.get("name", "")
        ).strip()

        hex_code = str(
            request.data.get("hex_code", "#000000")
        ).strip()

        if not name:
            raise ValidationError({
                "name": ["Color name is required."]
            })

        if (
            len(hex_code) != 7
            or not hex_code.startswith("#")
        ):
            raise ValidationError({
                "hex_code": [
                    "Use a hex color such as #000000."
                ]
            })

        existing = ProductColor.objects.filter(
            product=product,
            name__iexact=name,
        ).first()

        if existing:
            return Response({
                "message": "Color already exists.",
                "id": existing.pk,
                "name": existing.name,
                "hex_code": existing.hex_code,
            })

        color = ProductColor.objects.create(
            product=product,
            name=name,
            hex_code=hex_code,
        )

        # Changing the product catalog requires moderation again.
        product.moderation_status = Product.MODERATION_PENDING
        product.is_active = False
        product.save(
            update_fields=[
                "moderation_status",
                "is_active",
            ]
        )

        return Response({
            "message": "Color created.",
            "id": color.pk,
            "name": color.name,
            "hex_code": color.hex_code,
        }, status=201)

class VariantFormView(SellerKindView):
    def form(self, request, kind, pk, variant_pk=None, submitted=False):
        from .partners import catalog
        item = get_object_or_404(catalog(seller_for(request.user), kind), pk=pk)
        if kind == "shop":
            instance = get_object_or_404(ProductVariant, product=item, pk=variant_pk) if variant_pk else ProductVariant(product=item)
            cls = forms.modelform_factory(ProductVariant, fields=("color", "size", "price", "stock", "sku", "is_active"))
            form = cls(request.data if submitted else None, instance=instance)
            form.fields["color"].queryset = item.colors.all()
            form.fields["sku"].empty_value = None
        elif kind == "food":
            instance = get_object_or_404(MenuItemOption, item=item, pk=variant_pk) if variant_pk else MenuItemOption(item=item)
            cls = forms.modelform_factory(MenuItemOption, fields=("name", "price", "is_available"))
            form = cls(request.data if submitted else None, instance=instance)
        else:
            raise ValidationError("This catalog does not have variants.")
        return form

    def get(self, request, kind, pk, variant_pk=None):
        return Response(schema(self.form(request, kind, pk, variant_pk)))

    @transaction.atomic
    def post(self, request, kind, pk, variant_pk=None):
        from .partners import catalog
        item = get_object_or_404(catalog(seller_for(request.user), kind).select_for_update(), pk=pk)
        if variant_pk:
            model = ProductVariant if kind == "shop" else MenuItemOption
            get_object_or_404(model.objects.select_for_update(), pk=variant_pk)
        form = self.form(request, kind, pk, variant_pk, True)
        validate(form)
        form.save()
        if kind == "shop":
            item.moderation_status = Product.MODERATION_PENDING
            item.is_active = False
            item.save(update_fields=["moderation_status", "is_active"])
        return Response({"message": "Variant saved." + (" Product submitted for review." if kind == "shop" else "")})
