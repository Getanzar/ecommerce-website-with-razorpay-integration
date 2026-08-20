from django.contrib.auth.decorators import login_required
from .forms import ProductReviewForm
from orders.models import OrderItem
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from rest_framework import generics

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
from django.db.models import Q, Case, When, IntegerField, Prefetch

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

            Product.objects

            .filter(q, is_active=True)

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

    categories = Category.objects.prefetch_related(
        Prefetch(
            "products",
            queryset=Product.objects.filter(
                is_active=True,
                stock__gt=0
            )
        )
    )

    # New Arrivals
    new_arrivals = Product.objects.filter(
        is_active=True,
        stock__gt=0
    ).order_by("-created")[:8]

    # Trending (temporary)
    trending_products = Product.objects.filter(
        is_active=True,
        stock__gt=0
    ).order_by("?")[:8]

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

    products = Product.objects.filter(
        is_active=True
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
        Product,
        slug=slug,
        is_active=True
    )

    # Product gallery images
    extra_images = product.images.all()

    # Colors with their images
# Colors with images
    colors = (
        product.colors
        .order_by("display_order")
    )

    # Active variants grouped by color
    variants = (
        product.variants
        .filter(is_active=True)
        .select_related("color")
        .order_by(
            "color__display_order",
            "size"
        )
    )
    has_stock = variants.filter(stock__gt=0).exists()

    # Create color-wise size mapping
    color_sizes = {}

    for variant in variants:

        color_id = variant.color.id

        if color_id not in color_sizes:
            color_sizes[color_id] = []

        color_sizes[color_id].append({
            "id": variant.id,
            "size": variant.size,
            "stock": variant.stock,
            "price": variant.final_price,
        })


    # Approved reviews
    reviews = (
        product.reviews
        .filter(is_approved=True)
        .select_related("user")
    )


    review_form = ProductReviewForm()


    # Related products
    related_products = (
        Product.objects
        .filter(
            category=product.category,
            is_active=True,
            stock__gt=0
        )
        .exclude(id=product.id)
        .prefetch_related(
            "images",
            "colors"
        )
        .order_by("-created")[:4]
    )


    # Wishlist + review permission
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


    context = {

        "product": product,

        "extra_images": extra_images,

        # color images
        "colors": colors,

        # all variants
        "variants": variants,

        "has_stock": has_stock,

        # javascript will use this
        "color_sizes": color_sizes,

        "reviews": reviews,

        "review_form": review_form,

        "related_products": related_products,

        "is_in_wishlist": is_in_wishlist,

        "can_review": can_review,

    }


    return render(
        request,
        "products/product_detail.html",
        context
    )

# ----------------------
# API VIEWS
# ----------------------

class ProductList(generics.ListAPIView):
    queryset = Product.objects.filter(
        is_active=True,
        stock__gt=0
        )
    serializer_class = ProductSerializer

class ProductDetail(generics.RetrieveAPIView):
    queryset = Product.objects.filter(is_active=True, stock__gt=0)
    serializer_class = ProductSerializer
    lookup_field = 'slug'



# ----------------------
# CATEGORY & SUBCATEGORY VIEWS
# ----------------------

def category_page(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    subcategories = category.subcategories.filter(
    products__is_active=True
).distinct()
    return render(request, "products/category_page.html", {
    "category": category,
    "subcategories": subcategories,
})


def subcategory_products(request, sub_id):
    subcategory = get_object_or_404(SubCategory, id=sub_id)
    products = Product.objects.filter(
    subcategory=subcategory,
    is_active=True
)
    return render(request, "products/subcategory_products.html", {
        "subcategory": subcategory,
        "products": products,
    })

@login_required
def toggle_wishlist(request, product_id):

    product = get_object_or_404(Product, id=product_id)

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
        .filter(user=request.user)
        .select_related("product")
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
def add_review(request, product_id):

    product = get_object_or_404(Product, id=product_id)

    if request.method != "POST":
        return redirect(
            "product_detail_page",
            slug=product.slug
        )

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
