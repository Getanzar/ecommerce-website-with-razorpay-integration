from django.contrib.auth import authenticate
from datetime import timedelta
import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from rest_framework import generics, status, serializers as drf_serializers
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import EmailOTP, UserProfile
from accounts.utils import send_email_otp, send_password_reset_otp
from addresses.models import Address
from cart.models import Cart, CartItem
from products.catalog import in_stock_products, sellable_variants, with_storefront_variants
from products.models import Category, Product, ProductVariant, Wishlist
from food.models import FoodCartItem, FoodOrder, FoodOrderItem, MenuItem, MenuItemOption, Restaurant
from groceries.models import GroceryCartItem, GroceryCategory, GroceryOrder, GroceryOrderItem, GroceryProduct, GroceryStore
from orders.models import Order, OrderItem, OrderTimeline
from .checkout_delivery import order_location
from .throttles import PublicAuthView, EmailAuthView
from .input_validation import integer, decimal, checkout_items
from .models import AccountDeletionRequest, CheckoutSession, CustomerCareReply, CustomerCareRequest, NotificationPreference, PushDevice

from .serializers import AddressSerializer, CartItemSerializer, CategorySerializer, GroceryCategorySerializer, GroceryProductSerializer, GroceryStoreDetailSerializer, GroceryStoreSerializer, OrderSerializer, ProductDetailSerializer, ProductSerializer, RestaurantDetailSerializer, RestaurantSerializer, UserSerializer

class CatalogPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 50


def auth_payload(user, device_name="Mobile device"):
    from .authentication import issue_session
    return {"token": issue_session(user, device_name), "user": UserSerializer(user).data}


class SignupView(EmailAuthView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        email = str(request.data.get("email", "")).strip().lower()
        phone = str(request.data.get("phone", "")).replace(" ", "").replace("+91", "")
        password = str(request.data.get("password", ""))
        errors = {}
        if len(username) < 3: errors["username"] = ["Use at least 3 characters."]
        try:
            User._meta.get_field("username").clean(username, None)
        except ValidationError as exc:
            errors["username"] = exc.messages
        try:
            drf_serializers.EmailField(max_length=254).run_validation(email)
        except drf_serializers.ValidationError:
            errors["email"] = ["Enter a valid email address."]
        if not phone.isdigit() or len(phone) != 10: errors["phone"] = ["Enter a valid 10-digit mobile number."]
        try:
            validate_password(password, User(username=username, email=email))
        except ValidationError as exc:
            errors["password"] = exc.messages
        if User.objects.filter(username__iexact=username).exists(): errors["username"] = ["This username is already taken."]
        if User.objects.filter(email__iexact=email).exists(): errors["email"] = ["An account with this email already exists. Sign in or choose Finish email verification."]
        if UserProfile.objects.filter(phone=phone).exists(): errors["phone"] = ["This phone number is already registered."]
        if errors: return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password, is_active=False)
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.phone = phone
                profile.save(update_fields=["phone"])
                if not send_email_otp(user):
                    raise RuntimeError("Verification email could not be sent")
        except (IntegrityError, RuntimeError):
            # The atomic block rolls back only this attempt. Never delete an
            # existing inactive account after an integrity error.
            return Response({"message": "We could not create the account or send its verification email. Please try again."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        payload = {"message": "Verification code sent.", "email": email}
        if getattr(settings, "MOBILE_API_DEBUG_OTP", False):
            payload["debug_otp"] = EmailOTP.objects.get(user=user).otp
        return Response(payload, status=status.HTTP_201_CREATED)


class ResendSignupOTPView(EmailAuthView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        email = drf_serializers.EmailField(max_length=254).run_validation(request.data.get("email", "")).lower()
        user = User.objects.select_for_update().filter(email__iexact=email, is_active=False).first()
        # A suspended/deleted verified customer must never be reactivated by
        # signup recovery. Only a pending, unverified signup is eligible.
        pending = user and UserProfile.objects.filter(user=user, email_verified=False).exists() and EmailOTP.objects.filter(user=user).exists()
        if pending and not send_email_otp(user):
            transaction.set_rollback(True)
        # Identical response for unknown, active, disabled and pending accounts.
        return Response({"message": "If this email has an unfinished signup, a verification code has been sent. Check your inbox and spam folder.", "email": email, "retry_after": 60})


class VerifyOTPView(PublicAuthView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        code = str(request.data.get("otp", "")).strip()
        user = User.objects.select_for_update().filter(email__iexact=email, is_active=False).first()
        pending = user and UserProfile.objects.filter(user=user, email_verified=False).exists()
        otp = EmailOTP.objects.select_for_update().filter(user=user).first() if pending else None
        if not otp or otp.is_expired() or otp.attempts >= 5:
            return Response({"message": "The verification code is invalid or expired."}, status=status.HTTP_400_BAD_REQUEST)
        if otp.otp != code:
            otp.attempts += 1; otp.save(update_fields=["attempts"])
            return Response({"message": "The verification code is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = True; user.save(update_fields=["is_active"])
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_verified = True; profile.save(update_fields=["email_verified"])
        otp.delete()
        return Response(auth_payload(user, request.data.get("device_name", "Mobile device")))


class LoginView(PublicAuthView):
    permission_classes = [AllowAny]

    def post(self, request):
        identity = str(request.data.get("identity", "")).strip()
        password = str(request.data.get("password", ""))
        username = identity
        if "@" in identity:
            match = User.objects.filter(email__iexact=identity).first()
            username = match.username if match else identity
        user = authenticate(request=request, username=username, password=password)
        if not user:
            return Response({"message": "The email/username or password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(auth_payload(user, request.data.get("device_name", "Mobile device")))


class PasswordResetRequestView(EmailAuthView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = drf_serializers.EmailField(max_length=254).run_validation(request.data.get("email", "")).lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user:
            try:
                with transaction.atomic():
                    if not send_password_reset_otp(user):
                        transaction.set_rollback(True)
            except Exception:
                logging.getLogger(__name__).exception("Mobile password reset email could not be prepared")
        # Never reveal whether an account exists for an email address.
        return Response({"message": "If an active account uses that email, a reset code has been sent."})


class PasswordResetConfirmView(PublicAuthView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        code = str(request.data.get("otp", "")).strip()
        password = str(request.data.get("password", ""))
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        record = EmailOTP.objects.select_for_update().filter(user=user).first() if user else None
        if not record or record.is_expired() or record.attempts >= 5:
            return Response({"message": "The reset code is invalid or expired."}, status=400)
        if record.otp != code:
            record.attempts += 1
            record.save(update_fields=["attempts"])
            return Response({"message": "The reset code is invalid or expired."}, status=400)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            return Response({"message": " ".join(exc.messages)}, status=400)
        user.set_password(password)
        user.save(update_fields=["password"])
        Token.objects.filter(user=user).delete()
        from .models import DeviceSession
        DeviceSession.objects.filter(user=user).update(revoked_at=timezone.now())
        PushDevice.objects.filter(user=user).update(active=False)
        record.delete()
        return Response({"message": "Password changed. Sign in with your new password."})


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current = str(request.data.get("current_password", ""))
        password = str(request.data.get("new_password", ""))
        if not request.user.check_password(current):
            return Response({"message": "Your current password is incorrect."}, status=400)
        try:
            validate_password(password, request.user)
        except ValidationError as exc:
            return Response({"message": " ".join(exc.messages)}, status=400)
        request.user.set_password(password)
        request.user.save(update_fields=["password"])
        Token.objects.filter(user=request.user).delete()
        from .models import DeviceSession
        DeviceSession.objects.filter(user=request.user).update(revoked_at=timezone.now())
        PushDevice.objects.filter(user=request.user).update(active=False)
        return Response({"message": "Password changed. Sign in again on your devices."})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        from .models import DeviceSession
        if isinstance(request.auth, DeviceSession):
            DeviceSession.objects.filter(pk=request.auth.pk).update(revoked_at=timezone.now())
            PushDevice.objects.filter(session=request.auth).update(active=False)
        else:
            Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    def get_object(self): return self.request.user


class NotificationPreferenceView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        row,_=NotificationPreference.objects.get_or_create(user=request.user)
        return Response({"order_updates":row.order_updates,"payment_updates":row.payment_updates,"promotions":row.promotions})
    def patch(self,request):
        row,_=NotificationPreference.objects.get_or_create(user=request.user)
        for field in ("order_updates","payment_updates","promotions"):
            if field in request.data:
                if not isinstance(request.data[field], bool):
                    return Response({"message": "Notification preferences must be true or false."}, status=400)
                setattr(row,field,request.data[field])
        row.save();return self.get(request)


class PushDeviceView(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,request):
        token=str(request.data.get("expo_push_token","")).strip()
        if not token.startswith("ExponentPushToken[") and not token.startswith("ExpoPushToken["):return Response({"message":"Invalid Expo push token."},status=400)
        from .models import DeviceSession
        row,_=PushDevice.objects.update_or_create(expo_push_token=token,defaults={"user":request.user,"platform":str(request.data.get("platform",""))[:20],"active":True,"session":request.auth if isinstance(request.auth, DeviceSession) else None})
        return Response({"id":row.pk,"active":row.active},status=201)
    def delete(self,request):
        token=str(request.data.get("expo_push_token","")).strip()
        PushDevice.objects.filter(user=request.user,expo_push_token=token).update(active=False)
        return Response(status=204)


class AccountDeletionRequestView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        row=AccountDeletionRequest.objects.filter(user=request.user).first()
        return Response({"status": row.status if row else None})
    def post(self,request):
        row,_=AccountDeletionRequest.objects.update_or_create(user=request.user,defaults={"reason":str(request.data.get("reason",""))[:300],"status":"Pending"})
        Token.objects.filter(user=request.user).delete()
        from .models import DeviceSession
        DeviceSession.objects.filter(user=request.user).update(revoked_at=timezone.now())
        PushDevice.objects.filter(user=request.user).update(active=False)
        return Response({"id":row.pk,"status":row.status},status=201)


class CategoryListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    pagination_class = None
    def get_queryset(self):
        return Category.objects.filter(products__in=in_stock_products()).prefetch_related("subcategories").distinct().order_by("name")


class ProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    pagination_class = CatalogPagination
    def get_queryset(self):
        rows = in_stock_products().select_related("seller", "category")
        query = self.request.query_params.get("q", "").strip()
        category = self.request.query_params.get("category", "").strip()
        subcategory = self.request.query_params.get("subcategory", "").strip()

        gender = self.request.query_params.get("gender", "").strip()
        kids_age_group = self.request.query_params.get("kids_age_group", "").strip()

        seller = self.request.query_params.get("seller", "").strip()
        color = self.request.query_params.get("color", "").strip()
        size = self.request.query_params.get("size", "").strip()
        min_price = self.request.query_params.get("min_price", "").strip()
        max_price = self.request.query_params.get("max_price", "").strip()
        min_rating = self.request.query_params.get("rating", "").strip()
        ordering = self.request.query_params.get("sort", "newest").strip()
        if query: rows = rows.filter(Q(name__icontains=query) | Q(description__icontains=query))
        if category:
            if category.isdigit():
                rows = rows.filter(category_id=integer(category, "category"))
            else:
                rows = rows.filter(category__slug=category)
        if subcategory:
            rows = rows.filter(subcategory_id=integer(subcategory, "subcategory")) if subcategory.isdigit() else rows.filter(subcategory__name__iexact=subcategory)
        if gender:
            rows = rows.filter(gender=gender)

        if kids_age_group:
            rows = rows.filter(kids_age_group=kids_age_group)
        if seller:
            rows = rows.filter(seller_id=integer(seller, "seller")) if seller.isdigit() else rows.filter(seller__store_name__iexact=seller)
        if color: rows = rows.filter(variants__color__name__iexact=color)
        if size: rows = rows.filter(variants__size__iexact=size)
        minimum = decimal(min_price, "min_price") if min_price else None
        maximum = decimal(max_price, "max_price") if max_price else None
        if minimum is not None and maximum is not None and minimum > maximum:
            raise drf_serializers.ValidationError({"max_price": ["Maximum price must be at least the minimum price."]})
        if minimum is not None: rows = rows.filter(price__gte=minimum)
        if maximum is not None: rows = rows.filter(price__lte=maximum)
        if min_rating: rows = rows.filter(reviews__is_approved=True, reviews__rating__gte=decimal(min_rating, "rating", maximum=5))
        rows=rows.annotate(api_rating=Avg("reviews__rating", filter=Q(reviews__is_approved=True)), api_review_count=Count("reviews", filter=Q(reviews__is_approved=True), distinct=True))
        sort_map={"newest":"-created","price_low":"price","price_high":"-price","rating":"-api_rating","popularity":"-api_review_count"}
        return with_storefront_variants(rows.distinct()).order_by(sort_map.get(ordering,"-created"), "-created", "-pk")


class ProductDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"
    def get_queryset(self):
        return in_stock_products().select_related("seller", "category").prefetch_related("images", "variants__color")


class WishlistView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductSerializer
    def get_queryset(self):
        return with_storefront_variants(in_stock_products().filter(wishlisted_by__user=self.request.user).select_related("seller", "category"))


class WishlistItemView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, product_id):
        product = generics.get_object_or_404(in_stock_products(), pk=product_id)
        Wishlist.objects.get_or_create(user=request.user, product=product)
        return Response({"is_wishlisted": True}, status=status.HTTP_201_CREATED)
    def delete(self, request, product_id):
        Wishlist.objects.filter(user=request.user, product_id=product_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        items = cart.items.select_related("product", "product__category", "product__seller", "variant", "variant__color")
        data = CartItemSerializer(items, many=True, context={"request": request}).data
        return Response({"items": data, "item_count": sum(row.quantity for row in items), "subtotal": str(sum((row.variant.customer_price_with_tax if row.variant_id else row.product.storefront_price) * row.quantity for row in items))})
    def delete(self, request):
        CartItem.objects.filter(cart__user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemCreateView(APIView):
    permission_classes = [IsAuthenticated]
    @transaction.atomic
    def post(self, request):
        variant_id = integer(request.data.get("variant_id"), "variant_id")
        variant = generics.get_object_or_404(sellable_variants().select_related("product"), pk=variant_id)
        quantity = integer(request.data.get("quantity", 1), "quantity", maximum=10)
        if quantity > variant.stock: return Response({"quantity": ["The requested quantity is not available."]}, status=400)
        cart, _ = Cart.objects.get_or_create(user=request.user)
        # Older website sessions could create more than one row for the same
        # variant. Consolidate them here so mobile add-to-cart is idempotent.
        matches = list(CartItem.objects.select_for_update().filter(cart=cart, variant=variant).order_by("id"))
        created = not matches
        if matches:
            item = matches[0]
            existing_quantity = sum(row.quantity for row in matches)
            item.product = variant.product
            item.quantity = min(existing_quantity + quantity, variant.stock, 10)
            item.save(update_fields=["product", "quantity"])
            CartItem.objects.filter(pk__in=[row.pk for row in matches[1:]]).delete()
        else:
            item = CartItem.objects.create(cart=cart, product=variant.product, variant=variant, quantity=quantity)
        return Response(CartItemSerializer(item, context={"request": request}).data, status=201 if created else 200)


class CartItemView(APIView):
    permission_classes = [IsAuthenticated]
    def patch(self, request, item_id):
        item = generics.get_object_or_404(CartItem.objects.select_related("variant", "product"), pk=item_id, cart__user=request.user)
        quantity = integer(request.data.get("quantity"), "quantity", minimum=0, maximum=10)
        if quantity < 1: item.delete(); return Response(status=204)
        if quantity > 10 or (item.variant_id and quantity > item.variant.stock): return Response({"quantity": ["The requested quantity is not available."]}, status=400)
        item.quantity = quantity; item.save(update_fields=["quantity"])
        return Response(CartItemSerializer(item, context={"request": request}).data)
    def delete(self, request, item_id):
        generics.get_object_or_404(CartItem, pk=item_id, cart__user=request.user).delete()
        return Response(status=204)


class AddressListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AddressSerializer
    def get_queryset(self): return Address.objects.filter(user=self.request.user).order_by("-is_default", "-created_at")
    def perform_create(self, serializer):
        address = serializer.save(user=self.request.user)
        if not Address.objects.filter(user=self.request.user).exclude(pk=address.pk).exists():
            address.is_default = True; address.save(update_fields=["is_default"])


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AddressSerializer
    def get_queryset(self): return Address.objects.filter(user=self.request.user)


class DefaultAddressView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, pk):
        address = generics.get_object_or_404(Address, pk=pk, user=request.user)
        with transaction.atomic():
            Address.objects.filter(user=request.user, is_default=True).update(is_default=False)
            address.is_default = True; address.save(update_fields=["is_default"])
        return Response(AddressSerializer(address).data)


class RestaurantListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = RestaurantSerializer
    pagination_class = None
    def get_queryset(self):
        rows=Restaurant.objects.filter(seller__status="approved",accepts_orders=True).select_related("seller")
        pincode=self.request.query_params.get("pincode","").strip()
        if pincode: rows=rows.filter(service_areas__pincode=pincode,service_areas__is_active=True)
        return rows.distinct().order_by("name")


class RestaurantDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = RestaurantDetailSerializer
    lookup_field = "slug"
    def get_queryset(self):
        available_options = MenuItem.objects.filter(is_available=True).prefetch_related("options").select_related("section")
        return Restaurant.objects.filter(seller__status="approved").select_related("seller").prefetch_related("menu_items__options", "menu_items__section")


class GroceryStoreListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = GroceryStoreSerializer
    pagination_class = None
    def get_queryset(self):
        rows=GroceryStore.objects.filter(seller__status="approved",accepts_orders=True).select_related("seller")
        pincode=self.request.query_params.get("pincode","").strip()
        if pincode: rows=rows.filter(service_areas__pincode=pincode,service_areas__is_active=True)
        return rows.distinct().order_by("name")


class GroceryStoreDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = GroceryStoreDetailSerializer
    lookup_field = "slug"
    def get_queryset(self):
        rows = GroceryStore.objects.filter(seller__status="approved").select_related("seller")
        return rows if self.request.query_params.get("include_products") == "false" else rows.prefetch_related("products__category")


class GroceryCategoryListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = GroceryCategorySerializer
    pagination_class = None
    queryset = GroceryCategory.objects.all().order_by("display_order", "name")


class GroceryProductListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = GroceryProductSerializer
    pagination_class = CatalogPagination
    def get_queryset(self):
        rows = GroceryProduct.objects.filter(is_active=True, stock__gt=0, store__seller__status="approved").select_related("store", "category")
        store = self.request.query_params.get("store")
        category = self.request.query_params.get("category")
        query = self.request.query_params.get("q")
        if store: rows = rows.filter(store__slug=store)
        if category: rows = rows.filter(category__slug=category)
        if query: rows = rows.filter(Q(name__icontains=query) | Q(brand__icontains=query))
        return rows.order_by("category__display_order", "name", "pk")


def _food_cart_payload(request):
    rows = FoodCartItem.objects.filter(user=request.user).select_related("option__item__restaurant", "option__item__section")
    items = [{"id": row.pk, "option_id": row.option_id, "name": row.option.item.name, "option_name": row.option.name,
              "image_url": request.build_absolute_uri(row.option.item.image.url) if row.option.item.image else None,
              "restaurant_id": row.option.item.restaurant_id, "restaurant_name": row.option.item.restaurant.name,
              "quantity": row.quantity, "note": row.note, "unit_price": str(row.option.customer_price), "total": str(row.total)} for row in rows]
    return {"items": items, "item_count": sum(row.quantity for row in rows), "subtotal": str(sum(row.total for row in rows))}


class FoodCartView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request): return Response(_food_cart_payload(request))
    def delete(self, request): FoodCartItem.objects.filter(user=request.user).delete(); return Response(status=204)


class FoodCartItemCreateView(APIView):
    permission_classes = [IsAuthenticated]
    @transaction.atomic
    def post(self, request):
        option_id = integer(request.data.get("option_id"), "option_id")
        quantity = integer(request.data.get("quantity", 1), "quantity", maximum=20)
        option = generics.get_object_or_404(MenuItemOption.objects.select_related("item__restaurant"), pk=option_id, is_available=True, item__is_available=True)
        if not option.item.restaurant.accepts_orders: return Response({"message": "This restaurant is currently closed."}, status=409)
        different = FoodCartItem.objects.filter(user=request.user).exclude(option__item__restaurant_id=option.item.restaurant_id)
        if different.exists():
            if not request.data.get("replace_cart"): return Response({"message": "Your food cart contains items from another restaurant.", "replace_required": True}, status=409)
            different.delete()
        row, created = FoodCartItem.objects.get_or_create(user=request.user, option=option, defaults={"quantity": quantity, "note": str(request.data.get("note", ""))[:300]})
        if not created: row.quantity = min(row.quantity + quantity, 20); row.save(update_fields=("quantity", "updated_at"))
        return Response(_food_cart_payload(request), status=201 if created else 200)


class FoodCartItemView(APIView):
    permission_classes = [IsAuthenticated]
    def patch(self, request, item_id):
        row = generics.get_object_or_404(FoodCartItem, pk=item_id, user=request.user)
        quantity = integer(request.data.get("quantity", row.quantity), "quantity", minimum=0, maximum=20)
        if quantity < 1: row.delete()
        else: row.quantity = min(quantity, 20); row.note = str(request.data.get("note", row.note))[:300]; row.save()
        return Response(_food_cart_payload(request))
    def delete(self, request, item_id): generics.get_object_or_404(FoodCartItem, pk=item_id, user=request.user).delete(); return Response(_food_cart_payload(request))


def _grocery_cart_payload(request):
    rows = GroceryCartItem.objects.filter(user=request.user).select_related("product__store")
    items = [{"id": row.pk, "product_id": row.product_id, "name": row.product.name, "unit": row.product.unit,
              "image_url": request.build_absolute_uri(row.product.image.url) if row.product.image else None,
              "store_id": row.product.store_id, "store_name": row.product.store.name, "stock": row.product.stock,
              "quantity": row.quantity, "unit_price": str(row.product.customer_price), "total": str(row.total)} for row in rows]
    return {"items": items, "item_count": sum(row.quantity for row in rows), "subtotal": str(sum(row.total for row in rows))}


class GroceryCartView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request): return Response(_grocery_cart_payload(request))
    def delete(self, request): GroceryCartItem.objects.filter(user=request.user).delete(); return Response(status=204)


class GroceryCartItemCreateView(APIView):
    permission_classes = [IsAuthenticated]
    @transaction.atomic
    def post(self, request):
        product_id = integer(request.data.get("product_id"), "product_id")
        quantity = integer(request.data.get("quantity", 1), "quantity", maximum=20)
        product = generics.get_object_or_404(GroceryProduct.objects.select_for_update().select_related("store"), pk=product_id, is_active=True, stock__gt=0)
        if not product.store.accepts_orders: return Response({"message": "This grocery store is currently closed."}, status=409)
        different = GroceryCartItem.objects.filter(user=request.user).exclude(product__store_id=product.store_id)
        if different.exists():
            if not request.data.get("replace_cart"): return Response({"message": "Your grocery cart contains items from another store.", "replace_required": True}, status=409)
            different.delete()
        if quantity > product.stock: return Response({"quantity": [f"Only {product.stock} available."]}, status=409)
        row, created = GroceryCartItem.objects.get_or_create(user=request.user, product=product, defaults={"quantity": quantity})
        if not created: row.quantity = min(row.quantity + quantity, product.stock, 20); row.save(update_fields=("quantity", "updated_at"))
        return Response(_grocery_cart_payload(request), status=201 if created else 200)


class GroceryCartItemView(APIView):
    permission_classes = [IsAuthenticated]
    def patch(self, request, item_id):
        row = generics.get_object_or_404(GroceryCartItem.objects.select_related("product"), pk=item_id, user=request.user)
        quantity = integer(request.data.get("quantity", row.quantity), "quantity", minimum=0, maximum=20)
        if quantity < 1: row.delete()
        elif quantity > row.product.stock: return Response({"message": f"Only {row.product.stock} available."}, status=409)
        else: row.quantity = min(quantity, 20); row.save(update_fields=("quantity", "updated_at"))
        return Response(_grocery_cart_payload(request))
    def delete(self, request, item_id): generics.get_object_or_404(GroceryCartItem, pk=item_id, user=request.user).delete(); return Response(_grocery_cart_payload(request))


def _address_for(request):
    address_id = integer(request.data.get("address_id"), "address_id")
    return Address.objects.filter(pk=address_id, user=request.user).first()


def _quote_data(request, kind, address, location=None):
    from payments.pricing import DeliveryQuoteError, build_food_pricing, build_grocery_pricing, build_parcel_pricing
    from orders.commerce import _json_value
    location = location or {}
    delivery_quotes = []
    if kind == "shop":
        cart_rows=list(CartItem.objects.filter(cart__user=request.user).select_related("product__seller","variant","variant__color"))
        if not cart_rows:return None,"Your Shop cart is empty."
        if any(not row.variant_id or not row.variant.is_active or row.variant.stock < row.quantity for row in cart_rows):return None,"One or more Shop items changed or are unavailable."
        rows=[{"product":row.product,"variant":row.variant,"quantity":row.quantity} for row in cart_rows]
        local_sellers = [row.product.seller for row in cart_rows if row.product.seller and (row.product.seller.business_pincode or settings.DELHIVERY_ORIGIN_PINCODE) == address.pincode]
        if local_sellers and not location:return None,"Confirm the delivery address GPS location before continuing."
        if any(seller.business_latitude is None or seller.business_longitude is None for seller in local_sellers):return None,"A seller must verify their pickup location before accepting local orders."
        try: pricing, delivery_quotes=build_parcel_pricing(rows,{"pincode":address.pincode,**location},"cod")
        except DeliveryQuoteError as exc:return None,str(exc)
        snapshot=[{"id":row.pk,"variant_id":row.variant_id,"quantity":row.quantity,"price":str(row.variant.customer_price_with_tax)} for row in cart_rows]
        eta="3â€“7 business days"; source="ZIYAMART sellers"
    elif kind == "food":
        cart_rows=list(FoodCartItem.objects.filter(user=request.user).select_related("option__item__restaurant"))
        if not cart_rows:return None,"Your Food cart is empty."
        restaurant=cart_rows[0].option.item.restaurant
        if not location:return None,"Confirm the delivery address GPS location before continuing."
        if restaurant.latitude is None or restaurant.longitude is None:return None,"The restaurant must verify its pickup location before accepting orders."
        if restaurant.pincode != address.pincode:return None,"Local food delivery requires the same pincode."
        if not restaurant.accepts_orders or any(row.option.item.restaurant_id!=restaurant.pk or not row.option.is_available or not row.option.item.is_available for row in cart_rows):return None,"The restaurant or an item is currently unavailable."
        if not restaurant.service_areas.filter(pincode=address.pincode,is_active=True).exists():return None,"This restaurant does not deliver to the selected pincode."
        rows=[{"option":row.option,"quantity":row.quantity} for row in cart_rows]; pricing=build_food_pricing(rows,restaurant)
        if sum(row["option"].customer_price*row["quantity"] for row in rows)<restaurant.minimum_order:return None,f"Minimum order is â‚¹{restaurant.minimum_order}."
        snapshot=[{"id":row.pk,"option_id":row.option_id,"quantity":row.quantity,"price":str(row.option.customer_price)} for row in cart_rows]
        eta=f"About {restaurant.preparation_minutes + 20} minutes"; source=restaurant.name
    elif kind == "grocery":
        cart_rows=list(GroceryCartItem.objects.filter(user=request.user).select_related("product__store"))
        if not cart_rows:return None,"Your Grocery cart is empty."
        store=cart_rows[0].product.store
        if not location:return None,"Confirm the delivery address GPS location before continuing."
        if store.latitude is None or store.longitude is None:return None,"The store must verify its pickup location before accepting orders."
        if store.pincode != address.pincode or not store.service_areas.filter(pincode=address.pincode,is_active=True,delivery_mode="local").exists():return None,"Local grocery delivery is unavailable for this pincode."
        if not store.accepts_orders or any(row.product.store_id!=store.pk or not row.product.is_active or row.product.stock<row.quantity for row in cart_rows):return None,"The store, stock, or an item changed."
        if not store.service_areas.filter(pincode=address.pincode,is_active=True).exists():return None,"This store does not deliver to the selected pincode."
        rows=[{"product":row.product,"quantity":row.quantity} for row in cart_rows]; pricing=build_grocery_pricing(rows,store)
        if sum(row["product"].customer_price*row["quantity"] for row in rows)<store.minimum_order:return None,f"Minimum order is â‚¹{store.minimum_order}."
        snapshot=[{"id":row.pk,"product_id":row.product_id,"quantity":row.quantity,"price":str(row.product.customer_price)} for row in cart_rows]
        eta=f"About {store.estimated_delivery_minutes} minutes"; source=store.name
    else:return None,"Unknown checkout type."
    total=pricing["grand_total"]+pricing["customer_delivery_charge"]
    try: cod_limit=Decimal(str(getattr(settings,"MOBILE_COD_MAX_TOTAL","50000.00")))
    except InvalidOperation: cod_limit=Decimal("50000.00")
    cod_eligible=cod_limit<=0 or total<=cod_limit
    public={"kind":kind,"item_subtotal":str(pricing["grand_total"]),"delivery_charge":str(pricing["customer_delivery_charge"]),"discount":"0.00","total":str(total),"tax_inclusive":True,"delivery_mode":pricing["delivery_mode"],"eta":eta,"source":source,"cod_eligible":cod_eligible,"cod_unavailable_reason":"" if cod_eligible else f"Cash on delivery is available up to â‚¹{cod_limit}.","address":{"id":address.pk,"label":f"{address.address_line_1}, {address.city} {address.pincode}"}}
    address_snapshot = {key: getattr(address, key) for key in ("full_name", "phone", "address_line_1", "address_line_2", "city", "state", "pincode")}
    quotes = [_json_value({**{key:value for key,value in row.items() if key != "seller"}, "seller_id": row["seller"].pk if row["seller"] else None}) for row in delivery_quotes]
    fingerprint=hashlib.sha256(json.dumps({"items":snapshot,"address":address_snapshot,"location":location,"pricing":_json_value(pricing)},sort_keys=True).encode()).hexdigest()
    return {"public":public,"internal":{key:str(value) for key,value in pricing.items()},"snapshot":snapshot,"fingerprint":fingerprint,"location":location,"delivery_quotes":quotes},None


class CheckoutQuoteView(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,request,kind):
        address=_address_for(request)
        if not address:return Response({"message":"Select a valid delivery address."},status=400)
        from .checkout_delivery import DeliveryLocationSerializer
        location = {}
        if request.data.get("location") is not None:
            serializer = DeliveryLocationSerializer(data=request.data["location"])
            serializer.is_valid(raise_exception=True)
            location = dict(serializer.data)
        quote,error=_quote_data(request,kind,address,location)
        if error:return Response({"message":error},status=409)
        expires=timezone.now()+timedelta(minutes=10)
        session=CheckoutSession.objects.create(user=request.user,order_kind=kind,address_id=address.pk,cart_fingerprint=quote["fingerprint"],quote=quote,expires_at=expires)
        return Response({"quote_id":str(session.token),"expires_at":expires,"price":quote["public"]},status=201)


def _checkout_guard(request, kind, payment_method="cod"):
    quote_id=str(request.data.get("quote_id","")).strip(); key=str(request.data.get("idempotency_key","")).strip()
    if not quote_id or not key:return None,Response({"message":"Refresh the checkout quote before placing this order."},status=400)
    previous=CheckoutSession.objects.filter(user=request.user,order_kind=kind,idempotency_key=key,status="completed").first()
    if previous:
        from .payment_api import payment_payload
        return None, Response({**payment_payload(_owned_order(request.user, kind, previous.order_id), kind), "duplicate": True})
    session=generics.get_object_or_404(CheckoutSession.objects.select_for_update(),token=quote_id,user=request.user,order_kind=kind)
    if session.status == "completed":
        from .payment_api import payment_payload
        return None, Response({**payment_payload(_owned_order(request.user, kind, session.order_id), kind), "duplicate": True})
    requested_address_id = integer(request.data.get("address_id"), "address_id")
    if requested_address_id!=session.address_id:return None,Response({"message":"The delivery address changed. Refresh the quote."},status=409)
    if payment_method == "cod" and not session.quote.get("public",{}).get("cod_eligible",True):return None,Response({"message":session.quote["public"].get("cod_unavailable_reason","Cash on delivery is unavailable for this order.")},status=409)
    if session.expires_at<=timezone.now():return None,Response({"message":"This checkout quote expired. Refresh it and review the latest total.","quote_expired":True},status=409)
    address=Address.objects.filter(pk=session.address_id,user=request.user).first()
    quote,error=_quote_data(request,kind,address,session.quote.get("location")) if address else (None,"The selected address is no longer available.")
    if error:return None,Response({"message":error,"requote_required":True},status=409)
    if quote["fingerprint"]!=session.cart_fingerprint or quote["public"]["total"]!=session.quote["public"]["total"]:return None,Response({"message":"Price, stock, or availability changed. Please review a refreshed quote.","requote_required":True},status=409)
    if kind in {"food", "grocery"} and request.data.get("items"):
        item_key = "option_id" if kind == "food" else "product_id"
        try:
            submitted = sorted((row[item_key], row["quantity"]) for row in checkout_items(request.data["items"], item_key))
            quoted = sorted((int(row[item_key]), int(row["quantity"])) for row in session.quote["snapshot"])
        except (KeyError, TypeError, ValueError):
            return None, Response({"message": "Invalid checkout items."}, status=400)
        if submitted != quoted:
            return None, Response({"message": "Your items changed. Refresh the checkout quote.", "requote_required": True}, status=409)
    session.idempotency_key=key
    try:session.save(update_fields=["idempotency_key","updated_at"])
    except IntegrityError:return None,Response({"message":"This checkout submission is already being processed."},status=409)
    return session,None


def _complete_checkout(session, order):
    session.status="completed";session.order_id=order.pk;session.save(update_fields=["status","order_id","updated_at"])
    from .notifications import notify_sellers_of_order
    from .checkout_delivery import save_delivery_records, dispatch_local_parcel
    save_delivery_records(order, session.quote)
    notify_sellers_of_order(order)
    if session.order_kind == "shop":
        dispatch_local_parcel(order)


def _payment_method(request):
    value = str(request.data.get("payment_method", "cod")).lower()
    return value if value in {"cod", "online"} else None


def _razorpay_checkout(order, kind, snapshot):
    """Create one provider order for an already-reserved mobile order."""
    from payments.services import create_payment_transaction, create_razorpay_order
    total = getattr(order, "total_price", getattr(order, "total", 0))
    provider = create_razorpay_order(
        total,
        f"mobile-{kind}-{order.pk}",
        {"channel": kind, "order_id": str(order.pk), "user_id": str(order.user_id)},
    )
    order.razorpay_order_id = provider["id"]
    order.save(update_fields=["razorpay_order_id", "updated_at"])
    create_payment_transaction(order, provider["id"], snapshot=snapshot)
    return {
        "key_id": settings.RAZORPAY_KEY_ID,
        "order_id": provider["id"],
        "amount": int(Decimal(str(total)) * 100),
        "currency": "INR",
        "name": "ZIYAMART",
        "description": f"ZIYAMART {kind.title()} order #{order.pk}",
    }


def _checkout_response(order, kind, payment=None):
    total = getattr(order, "total_price", getattr(order, "total", 0))
    payload = {"id": order.pk, "kind": kind, "total": str(total), "status": order.status,
               "payment_method": order.payment_method, "payment_status": order.payment_status}
    if payment:
        payload["razorpay"] = payment
    return payload


class ParcelCheckoutView(APIView):
    """Create a real COD marketplace order from the authenticated database cart."""
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        payment_method = _payment_method(request)
        if not payment_method: return Response({"message": "Choose a valid payment method."}, status=400)
        checkout,error=_checkout_guard(request,"shop", payment_method)
        if error:return error
        address = _address_for(request)
        if not address: return Response({"message": "Select a valid delivery address."}, status=400)
        # PostgreSQL cannot lock the nullable variant/color side of this join.
        # Lock cart rows here and inventory separately, in stable primary-key order.
        rows = list(CartItem.objects.select_for_update(of=("self",)).filter(cart__user=request.user).select_related("product", "variant", "variant__color").order_by("pk"))
        if not rows: return Response({"message": "Your cart is empty."}, status=400)
        locked_variants = {v.pk: v for v in ProductVariant.objects.select_for_update(of=("self",)).filter(
            pk__in=[row.variant_id for row in rows if row.variant_id]
        ).select_related("product__seller", "color").order_by("pk")}
        for row in rows:
            row.variant = locked_variants.get(row.variant_id)
        if any(not row.variant_id or not row.variant.is_active or row.variant.stock < row.quantity for row in rows):
            return Response({"message": "One or more items are no longer available in the requested quantity."}, status=409)
        total = sum(row.variant.customer_price_with_tax * row.quantity for row in rows)
        order = Order.objects.create(user=request.user, full_name=address.full_name, phone=address.phone,
            address=f"{address.address_line_1}{', ' + address.address_line_2 if address.address_line_2 else ''}",
            city=address.city, state=address.state, pincode=address.pincode, total_price=total,
            payment_method=payment_method, payment_status="Pending", **order_location(checkout.quote))
        for row in rows:
            variant = row.variant
            OrderItem.objects.create(order=order, product=row.product, variant=variant, product_name=row.product.name,
                product_image=row.product.image, product_color=variant.color.name, product_size=variant.size,
                product_sku=variant.sku or "", quantity=row.quantity, price=variant.customer_price_with_tax,
                seller_unit_price=variant.seller_price)
            variant.stock -= row.quantity; variant.save(update_fields=["stock"])
        CartItem.objects.filter(pk__in=[row.pk for row in rows]).delete()
        from payments.services import create_breakdown, create_payment_transaction
        pricing=checkout.quote["internal"];create_breakdown(order,pricing)
        payment = _razorpay_checkout(order, "shop", checkout.quote) if payment_method == "online" else None
        if payment is None: create_payment_transaction(order,snapshot=checkout.quote)
        _complete_checkout(checkout,order)
        return Response(_checkout_response(order, "shop", payment), status=201)


class FoodCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        payment_method = _payment_method(request)
        if not payment_method: return Response({"message": "Choose a valid payment method."}, status=400)
        checkout,error=_checkout_guard(request,"food", payment_method)
        if error:return error
        address = _address_for(request)
        if not address: return Response({"message": "Select a valid delivery address."}, status=400)
        submitted = checkout_items(request.data["items"], "option_id") if request.data.get("items") else [{"option_id": row.option_id, "quantity": row.quantity, "note": row.note} for row in FoodCartItem.objects.filter(user=request.user)]
        option_ids = [row.get("option_id") for row in submitted]
        options = {row.pk: row for row in MenuItemOption.objects.select_related("item__restaurant", "item__restaurant__seller").filter(pk__in=option_ids, is_available=True, item__is_available=True)}
        if not submitted or len(options) != len(set(option_ids)): return Response({"message": "Some food items are unavailable."}, status=409)
        restaurant = next(iter(options.values())).item.restaurant
        if not restaurant.accepts_orders or any(o.item.restaurant_id != restaurant.pk for o in options.values()): return Response({"message": "Order from one open restaurant at a time."}, status=400)
        if restaurant.pincode != address.pincode or not restaurant.service_areas.filter(pincode=address.pincode, is_active=True).exists(): return Response({"message": "This restaurant does not deliver to your address pincode."}, status=400)
        rows=[]
        for submitted_row in submitted:
            option=options[submitted_row["option_id"]]; quantity=max(1,min(int(submitted_row.get("quantity",1)),20)); rows.append({"option":option,"quantity":quantity})
        from payments.pricing import build_food_pricing
        pricing=build_food_pricing(rows,restaurant)
        if sum(row["option"].customer_price*row["quantity"] for row in rows) < restaurant.minimum_order: return Response({"message": f"Minimum order is â‚¹{restaurant.minimum_order}."}, status=400)
        order=FoodOrder.objects.create(user=request.user,restaurant=restaurant,full_name=address.full_name,phone=address.phone,address=address.address_line_1,city=address.city,state=address.state,pincode=address.pincode,subtotal=pricing["merchant_subtotal"]+pricing["platform_fee"],delivery_fee=restaurant.delivery_fee,total=pricing["grand_total"],**order_location(checkout.quote),payment_method=payment_method,include_cutlery=bool(request.data.get("include_cutlery")),delivery_note=str(request.data.get("delivery_note", ""))[:300])
        for row, submitted_row in zip(rows,submitted):
            option=row["option"]; FoodOrderItem.objects.create(order=order,menu_item=option.item,option=option,item_name=option.item.name,option_name=option.name,unit_price=option.customer_price,quantity=row["quantity"],customer_note=str(submitted_row.get("note", ""))[:300])
        FoodCartItem.objects.filter(user=request.user).delete()
        from payments.services import create_breakdown, create_payment_transaction
        create_breakdown(order,pricing)
        payment = _razorpay_checkout(order, "food", checkout.quote) if payment_method == "online" else None
        if payment is None: create_payment_transaction(order,snapshot=checkout.quote)
        _complete_checkout(checkout,order)
        return Response(_checkout_response(order, "food", payment),status=201)


class GroceryCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        payment_method = _payment_method(request)
        if not payment_method: return Response({"message": "Choose a valid payment method."}, status=400)
        checkout,error=_checkout_guard(request,"grocery", payment_method)
        if error:return error
        address = _address_for(request)
        if not address: return Response({"message": "Select a valid delivery address."}, status=400)
        submitted = checkout_items(request.data["items"], "product_id") if request.data.get("items") else [{"product_id": row.product_id, "quantity": row.quantity} for row in GroceryCartItem.objects.filter(user=request.user)]
        ids=[row.get("product_id") for row in submitted]
        products={p.pk:p for p in GroceryProduct.objects.select_for_update().select_related("store__seller").filter(pk__in=ids,is_active=True)}
        if not submitted or len(products)!=len(set(ids)): return Response({"message":"Some grocery items are unavailable."},status=409)
        store=next(iter(products.values())).store
        if not store.accepts_orders or any(p.store_id!=store.pk for p in products.values()): return Response({"message":"Order from one open grocery store at a time."},status=400)
        if store.pincode!=address.pincode or not store.service_areas.filter(pincode=address.pincode,is_active=True).exists(): return Response({"message":"This store does not deliver to your address pincode."},status=400)
        rows=[]
        for submitted_row in submitted:
            product=products[submitted_row["product_id"]]; quantity=max(1,min(int(submitted_row.get("quantity",1)),20))
            if product.stock<quantity:return Response({"message":f"Only {product.stock} of {product.name} available."},status=409)
            rows.append({"product":product,"quantity":quantity})
        from payments.pricing import build_grocery_pricing
        pricing=build_grocery_pricing(rows,store)
        if sum(row["product"].customer_price*row["quantity"] for row in rows)<store.minimum_order:return Response({"message":f"Minimum order is â‚¹{store.minimum_order}."},status=400)
        substitution=str(request.data.get("substitution_preference", "contact"))
        if substitution not in ("contact", "refund"): return Response({"message":"Choose a valid substitution preference."},status=400)
        order=GroceryOrder.objects.create(user=request.user,store=store,full_name=address.full_name,phone=address.phone,address=address.address_line_1,city=address.city,state=address.state,pincode=address.pincode,subtotal=pricing["merchant_subtotal"]+pricing["platform_fee"],delivery_fee=store.delivery_fee,total=pricing["grand_total"],**order_location(checkout.quote),payment_method=payment_method,delivery_mode="local",substitution_preference=substitution)
        for row in rows:
            product=row["product"]; GroceryOrderItem.objects.create(order=order,product=product,product_name=product.name,unit=product.unit,unit_price=product.customer_price,quantity=row["quantity"]); product.stock-=row["quantity"]; product.save(update_fields=["stock"])
        GroceryCartItem.objects.filter(user=request.user).delete()
        from payments.services import create_breakdown, create_payment_transaction
        create_breakdown(order,pricing)
        payment = _razorpay_checkout(order, "grocery", checkout.quote) if payment_method == "online" else None
        if payment is None: create_payment_transaction(order,snapshot=checkout.quote)
        _complete_checkout(checkout,order)
        return Response(_checkout_response(order, "grocery", payment),status=201)


def _unified_order(request, order, kind):
    if kind == "shop":
        items=[{"id":r.pk,"product_name":r.product_name,"product_color":r.product_color,"product_size":r.product_size,"quantity":r.quantity,"price":str(r.price),"line_total":str(r.total),"image_url":request.build_absolute_uri(r.product_image.url) if r.product_image else None} for r in order.items.all()]
        total=order.total_price; can_cancel=order.status in ("Pending","Processing"); can_return=order.can_request_return
        tracking=order.tracking_number; courier=order.courier
    elif kind == "food":
        items=[{"id":r.pk,"product_name":r.item_name,"product_color":"","product_size":r.option_name,"quantity":r.quantity,"price":str(r.unit_price),"line_total":str(r.line_total),"image_url":request.build_absolute_uri(r.menu_item.image.url) if r.menu_item.image else None} for r in order.items.all()]
        total=order.total; can_cancel=order.status in ("placed","accepted"); can_return=False; tracking=""; courier=order.restaurant.name
    else:
        items=[{"id":r.pk,"product_name":r.product_name,"product_color":"","product_size":r.unit,"quantity":r.quantity,"price":str(r.unit_price),"line_total":str(r.total),"image_url":request.build_absolute_uri(r.product.image.url) if r.product.image else None} for r in order.items.all()]
        total=order.total; can_cancel=order.status in ("placed","accepted"); can_return=False; tracking=order.tracking_number; courier=order.courier or order.store.name
    care={r.request_type:{"id":r.pk,"status":r.status,"reason":r.reason,"message":r.message,"created_at":r.created_at} for r in CustomerCareRequest.objects.filter(user=request.user,order_kind=kind,order_id=order.pk)}
    if kind=="shop": timeline=[{"event":r.event,"description":r.description,"created_at":r.created_at} for r in order.timeline.all()]
    else: timeline=[{"event":"Order placed","description":f"Your {kind} order was received.","created_at":order.created_at}]
    if not timeline: timeline=[{"event":"Order placed","description":"Your order was received.","created_at":order.created_at}]
    can_cancel = can_cancel and order.payment_method == "cod"
    return {"id":order.pk,"kind":kind,"created_at":order.created_at,"updated_at":order.updated_at,"total_price":str(total),"status":order.status,"payment_method":order.payment_method,"payment_status":order.payment_status,"can_cancel":can_cancel,"can_return":can_return,"items":items,"tracking_number":tracking,"courier":courier,"care":care,"timeline":timeline}


class OrderListView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        rows=[]
        rows += [_unified_order(request,o,"shop") for o in Order.objects.filter(user=request.user).prefetch_related("items","timeline")]
        rows += [_unified_order(request,o,"food") for o in FoodOrder.objects.filter(user=request.user).select_related("restaurant").prefetch_related("items__menu_item")]
        rows += [_unified_order(request,o,"grocery") for o in GroceryOrder.objects.filter(user=request.user).select_related("store").prefetch_related("items__product")]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        return Response(rows)


def _owned_order(user, kind, order_id):
    models={"shop":Order,"food":FoodOrder,"grocery":GroceryOrder}
    model=models.get(kind)
    if model is None:
        raise drf_serializers.ValidationError("Unknown order type.")
    return generics.get_object_or_404(model, pk=order_id, user=user)


class OrderCancelView(APIView):
    permission_classes=[IsAuthenticated]
    @transaction.atomic
    def post(self,request,kind,order_id):
        order=_owned_order(request.user,kind,order_id)
        order = type(order).objects.select_for_update().get(pk=order.pk)
        if order.payment_method != "cod":
            return Response({"message": "Online order cancellations require payment reconciliation. Open a support request for this order."}, status=409)
        allowed={"shop":("Pending","Processing"),"food":("placed","accepted"),"grocery":("placed","accepted")}
        if order.status not in allowed[kind]: return Response({"message":"This order can no longer be cancelled."},status=409)
        reason=str(request.data.get("reason","")).strip()
        if len(reason)<3:return Response({"message":"Please provide a cancellation reason."},status=400)
        if kind=="shop":
            for row in order.items.select_related("variant"):
                if row.variant_id: row.variant.stock += row.quantity; row.variant.save(update_fields=["stock"])
            order.status="Cancelled"
            order.cancel_reason=reason; order.cancelled_at=timezone.now()
        elif kind=="food": order.status="cancelled"
        else:
            for row in order.items.select_related("product"): row.product.stock += row.quantity; row.product.save(update_fields=["stock"])
            order.status="cancelled"
        fields=["status","updated_at"]
        if kind=="shop":
            fields += ["cancel_reason","cancelled_at"]
            OrderTimeline.objects.create(order=order,event="Cancelled",description=reason,performed_by=request.user)
        order.save(update_fields=fields)
        return Response(_unified_order(request,order,kind))


class OrderCareRequestView(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,request,kind,order_id):
        order=_owned_order(request.user,kind,order_id); request_type=str(request.data.get("request_type","support"))
        if request_type not in ("support","return"):return Response({"message":"Choose support or return."},status=400)
        if request_type=="return" and not (kind=="shop" and order.can_request_return):return Response({"message":"This order is not currently eligible for return."},status=409)
        reason=str(request.data.get("reason","")).strip(); message=str(request.data.get("message","")).strip()
        if len(reason)<3 or len(message)<5:return Response({"message":"Add a reason and a short description."},status=400)
        row,created=CustomerCareRequest.objects.get_or_create(user=request.user,order_kind=kind,order_id=order.pk,request_type=request_type,defaults={"reason":reason,"message":message})
        if not created:return Response({"message":"A request already exists for this order.","status":row.status},status=409)
        return Response({"id":row.pk,"status":row.status,"request_type":row.request_type},status=201)


def _care_data(request,row):
    return {"id":row.pk,"order_kind":row.order_kind,"order_id":row.order_id,"order_item_id":row.order_item_id,"request_type":row.request_type,"reason":row.reason,"message":row.message,"status":row.status,"attachment_url":request.build_absolute_uri(row.attachment.url) if row.attachment else None,"created_at":row.created_at,"replies":[{"id":reply.pk,"message":reply.message,"is_staff":reply.is_staff,"attachment_url":request.build_absolute_uri(reply.attachment.url) if reply.attachment else None,"created_at":reply.created_at} for reply in row.replies.all()]}


class SupportInput(drf_serializers.Serializer):
    reason = drf_serializers.CharField(min_length=3, max_length=100)
    message = drf_serializers.CharField(min_length=5, max_length=5000)
    order_kind = drf_serializers.ChoiceField(choices=["shop", "food", "grocery"], default="shop")
    order_id = drf_serializers.IntegerField(required=False, allow_null=True, min_value=1)
    order_item_id = drf_serializers.IntegerField(required=False, allow_null=True, min_value=1)
    request_type = drf_serializers.ChoiceField(choices=["support"], default="support")
    attachment = drf_serializers.ImageField(required=False)

    def validate_attachment(self, value):
        if value.size > 8 * 1024 * 1024:
            raise drf_serializers.ValidationError("Choose an image smaller than 8 MB.")
        return value


class SupportReplyInput(drf_serializers.Serializer):
    message = drf_serializers.CharField(min_length=2, max_length=5000)
    attachment = drf_serializers.ImageField(required=False)
    validate_attachment = SupportInput.validate_attachment


class CustomerCareListCreateView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        rows=CustomerCareRequest.objects.filter(user=request.user).prefetch_related("replies")
        return Response([_care_data(request,row) for row in rows])
    def post(self,request):
        payload=SupportInput(data=request.data)
        payload.is_valid(raise_exception=True)
        data=dict(payload.validated_data)
        order_id=data.get("order_id")
        if data.get("order_item_id") and not order_id:
            raise drf_serializers.ValidationError("Choose an order before choosing an item.")
        if order_id:
            order=_owned_order(request.user,data["order_kind"],order_id)
            if data.get("order_item_id"):
                generics.get_object_or_404(order.items,pk=data["order_item_id"])
            row,created=CustomerCareRequest.objects.get_or_create(user=request.user,order_kind=data["order_kind"],order_id=order_id,request_type="support",defaults={key:value for key,value in data.items() if key not in {"order_kind","order_id","request_type"}})
            if not created:return Response({"message":"A support request already exists for this order."},status=409)
        else:
            row=CustomerCareRequest.objects.create(user=request.user,**data)
        return Response(_care_data(request,row),status=201)


class CustomerCareReplyView(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,request,pk):
        ticket=generics.get_object_or_404(CustomerCareRequest,pk=pk,user=request.user)
        message=str(request.data.get("message","")).strip()
        payload=SupportReplyInput(data=request.data)
        payload.is_valid(raise_exception=True)
        CustomerCareReply.objects.create(request=ticket,user=request.user,**payload.validated_data)
        return Response(_care_data(request,ticket),status=201)


class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items")
