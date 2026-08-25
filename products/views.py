import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from .forms import ProductReviewForm
from orders.models import OrderItem
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from rest_framework import generics
from django.core.paginator import Paginator
from django.templatetags.static import static
from django.views.decorators.http import require_POST

from .models import (
    Category,
    Product,
    SubCategory,
    ProductColor,
    ProductVariant,
    ProductReview,
    Wishlist,
)

from .serializers import ProductSerializer
from django.db.models import Avg, Count, Q, Case, When, IntegerField, Prefetch
from .catalog import in_stock_products, public_products, with_storefront_variants

# ----------------------
# FRONTEND VIEWS
# ----------------------



def search_view(request):

    query = request.GET.get("q", "").strip().lower()

    results = Product.objects.none()

    if query:

        words = query.split()

        synonym_map = {

            # Gender
            "girl": "women",
            "girls": "women",
            "lady": "women",
            "ladies": "women",
            "female": "women",

            "boy": "kids",
            "boys": "kids",
            "child": "kids",
            "children": "kids",
            "kid": "kids",

            "man": "men",
            "men": "men",

            # Product types
            "tee": "shirt",
            "tshirt": "shirt",
            "t-shirt": "shirt",

            "pant": "jeans",
            "pants": "jeans",
            "trouser": "jeans",

            # Shopping language
            "new": "latest",
            "arrival": "latest",
            "arrivals": "latest",
        }

        q = Q()

        cheap = False
        expensive = False
        latest = False

        for word in words:

            word = synonym_map.get(word, word)

            if word in ["cheap", "budget", "lowest"]:
                cheap = True
                continue

            if word in ["premium", "expensive", "costly"]:
                expensive = True
                continue

            if word in ["latest", "newest"]:
                latest = True
                continue

            q &= (

                Q(name__icontains=word)

                |

                Q(description__icontains=word)

                |

                Q(category__name__icontains=word)

                |

                Q(subcategory__name__icontains=word)

                |

                Q(product_type__icontains=word)

                |

                Q(colors__name__icontains=word)

                |

                Q(variants__size__icontains=word)

            )

        results = (

            with_storefront_variants(in_stock_products(Product.objects.filter(q)))

            .select_related("category", "seller")

            .distinct()

            .annotate(

                priority=Case(

                    When(name__icontains=query, then=0),

                    default=1,

                    output_field=IntegerField(),

                )

            )

        )

        if latest:

            results = results.order_by("-created")

        elif cheap:

            results = results.order_by("price")

        elif expensive:

            results = results.order_by("-price")

        else:

            results = results.order_by("priority", "-created")

    return render(

        request,

        "products/search_results.html",

        {

            "results": results,

            "query": query,

        },

    )




def home(request):
    storefront_products = in_stock_products().select_related("category", "seller").annotate(
        approved_review_count=Count(
            "reviews",
            filter=Q(reviews__is_approved=True),
            distinct=True,
        ),
        storefront_rating=Avg(
            "reviews__rating",
            filter=Q(reviews__is_approved=True),
        ),
    )

    categories = (
        Category.objects.filter(products__in=in_stock_products())
        .distinct()
        .order_by("name")
    )

    new_arrivals = with_storefront_variants(storefront_products).order_by("-created")[:8]
    trending_products = with_storefront_variants(storefront_products).order_by(
        "-approved_review_count",
        "-storefront_rating",
        "-created",
    )[:8]

    return render(
        request,
        "home.html",
        {
            "categories": categories,
            "new_arrivals": new_arrivals,
            "trending_products": trending_products,
        },
    )

def product_list_page(request):

    products = with_storefront_variants(
        in_stock_products().select_related("category", "seller")
    ).order_by('-created')

    return render(
        request,
        'products/product_list.html',
        {
            'products': products
        }
    )

def product_detail_page(request, slug):
    product = get_object_or_404(
        public_products(Product.objects.select_related("category", "seller")),
        slug=slug,
    )
    extra_images = list(product.images.order_by("display_order", "id"))
    colors = product.colors.filter(variants__is_active=True).distinct().order_by("display_order", "id")
    variants = list(
        product.variants
        .filter(is_active=True)
        .select_related("color")
        .order_by("color__display_order", "size")
    )
    in_stock_variants = [variant for variant in variants if variant.stock > 0]
    has_stock = bool(in_stock_variants)
    starting_price = min(
        (variant.customer_price_with_tax for variant in in_stock_variants),
        default=product.customer_price_with_tax,
    )
    color_sizes = {}
    for variant in variants:
        color_id = variant.color.id
        if color_id not in color_sizes:
            color_sizes[color_id] = []
        color_sizes[color_id].append({
            "id": variant.id,
            "size": variant.size,
            "stock": variant.stock,
            "price": variant.customer_price_with_tax,
        })
    reviews_queryset = (
        product.reviews
        .filter(is_approved=True)
        .select_related("user")
    )
    review_stats = reviews_queryset.aggregate(average=Avg("rating"), count=Count("id"))
    review_count = review_stats["count"]
    rating_average = round(review_stats["average"], 1) if review_stats["average"] is not None else 0
    reviews = Paginator(reviews_queryset, 10).get_page(request.GET.get("reviews"))
    review_form = ProductReviewForm()
    related_products = (
        with_storefront_variants(in_stock_products(Product.objects.filter(category=product.category)))
        .exclude(id=product.id)
        .select_related("category", "seller")
        .prefetch_related("images", "colors")
        .order_by("-created")[:4]
    )
    is_in_wishlist = False
    can_review = False
    if request.user.is_authenticated:
        is_in_wishlist = Wishlist.objects.filter(
            user=request.user,
            product=product
        ).exists()
        can_review = OrderItem.objects.filter(
            product=product,
            order__user=request.user,
            order__status="Delivered"
        ).exists()
    product_image_url = request.build_absolute_uri(
        product.image.url if product.image else static("images/product-placeholder.svg")
    )
    schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "description": product.description,
        "image": [product_image_url],
        "sku": str(product.pk),
        "brand": {"@type": "Brand", "name": product.seller.store_name if product.seller_id else "ZIYAMART"},
        "offers": {
            "@type": "Offer",
            "url": request.build_absolute_uri(),
            "priceCurrency": "INR",
            "price": str(starting_price),
            "availability": "https://schema.org/InStock" if has_stock else "https://schema.org/OutOfStock",
        },
    }
    if review_count:
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": str(rating_average),
            "reviewCount": str(review_count),
        }
    context = {
        "product": product,
        "extra_images": extra_images,
        "colors": colors,
        "variants": variants,
        "has_stock": has_stock,
        "color_sizes": color_sizes,
        "reviews": reviews,
        "review_count": review_count,
        "rating_average": rating_average,
        "review_form": review_form,
        "related_products": related_products,
        "is_in_wishlist": is_in_wishlist,
        "can_review": can_review,
        "starting_price": starting_price,
        "product_image_url": product_image_url,
        "product_schema_json": (
            json.dumps(schema)
            .replace("<", "\\u003C")
            .replace(">", "\\u003E")
            .replace("&", "\\u0026")
        ),
        "meta_description": (product.description or f"Buy {product.name} on ZIYAMART")[:160],
        "return_window_days": getattr(settings, "RETURN_WINDOW_DAYS", 7),
    }
    return render(request, "products/product_detail.html", context)

# ----------------------
# API VIEWS
# ----------------------

class ProductList(generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        return with_storefront_variants(in_stock_products().select_related("seller"))

class ProductDetail(generics.RetrieveAPIView):
    serializer_class = ProductSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return public_products().select_related("seller")



# ----------------------
# CATEGORY & SUBCATEGORY VIEWS
# ----------------------

def category_page(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    subcategories = category.subcategories.filter(
        products__in=in_stock_products()
    ).distinct()
    return render(request, "products/category_page.html", {
    "category": category,
    "subcategories": subcategories,
})


def subcategory_products(request, sub_id):
    subcategory = get_object_or_404(SubCategory, id=sub_id)
    products = with_storefront_variants(in_stock_products(Product.objects.filter(
        subcategory=subcategory,
    )).select_related("seller", "category"))
    return render(request, "products/subcategory_products.html", {
        "subcategory": subcategory,
        "products": products,
    })

@login_required
@require_POST
def toggle_wishlist(request, product_id):
    product = get_object_or_404(public_products(), id=product_id)

    wishlist_item = Wishlist.objects.filter(
        user=request.user,
        product=product
    )

    if wishlist_item.exists():
        wishlist_item.delete()
    else:
        Wishlist.objects.create(
            user=request.user,
            product=product
        )

    return redirect(
        "product_detail_page",
        slug=product.slug
    )

@login_required
def wishlist_page(request):

    wishlist_items = (
        Wishlist.objects
        .filter(user=request.user, product__in=public_products())
        .select_related("product", "product__seller")
        .prefetch_related(Prefetch(
            "product__variants",
            queryset=ProductVariant.objects.filter(is_active=True, stock__gt=0).select_related("color"),
            to_attr="storefront_variants",
        ))
        .order_by("-created_at")
    )

    return render(
        request,
        "products/wishlist.html",
        {
            "wishlist_items": wishlist_items,
        }
    )

@login_required
@require_POST
def add_review(request, product_id):
    product = get_object_or_404(public_products(), id=product_id)

    # Only delivered orders can review
    has_purchased = OrderItem.objects.filter(
        product=product,
        order__user=request.user,
        order__status="Delivered"
    ).exists()

    if not has_purchased:

        messages.error(
            request,
            "Only customers who purchased and received this product can write a review."
        )

        return redirect(
            "product_detail_page",
            slug=product.slug
        )

    review = ProductReview.objects.filter(
        product=product,
        user=request.user
    ).first()

    form = ProductReviewForm(
        request.POST,
        instance=review
    )

    if form.is_valid():

        review = form.save(commit=False)

        review.product = product
        review.user = request.user
        review.is_verified_purchase = True

        review.save()

        messages.success(
            request,
            "Thank you for your review!"
        )
    else:
        messages.error(
            request,
            "Please correct your review: " + " ".join(
                error for errors in form.errors.values() for error in errors
            ),
        )

    return redirect(
        "product_detail_page",
        slug=product.slug
    )

@login_required
def my_reviews(request):

    reviews = (
        ProductReview.objects
        .filter(user=request.user)
        .select_related("product")
        .order_by("-created_at")
    )

    return render(
        request,
        "products/my_reviews.html",
        {
            "reviews": reviews,
        }
    )
