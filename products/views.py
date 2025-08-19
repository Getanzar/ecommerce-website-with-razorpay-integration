from django.shortcuts import render, get_object_or_404, redirect
from rest_framework import generics
from django.contrib import messages
from .models import Category, Product
from .serializers import ProductSerializer

# ----------------------
# FRONTEND VIEWS
# ----------------------

def home(request):
    # Get all categories with their related products
    categories = Category.objects.prefetch_related('products').all()
    return render(request, 'home.html', {'categories': categories})

def product_list_page(request):
    # List all products ordered by newest first
    products = Product.objects.all().order_by('-created')
    return render(request, 'products/product_list.html', {'products': products})

def product_detail_page(request, slug):
    product = get_object_or_404(Product, slug=slug)
    
    # ✅ prepare related products
    related_products = Product.objects.filter(category=product.category).exclude(id=product.id)[:4]
    
    context = {
        'product': product,
        'related_products': related_products
    }
    return render(request, 'products/product_detail.html', context)

# ----------------------
# API VIEWS
# ----------------------

class ProductList(generics.ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

class ProductDetail(generics.RetrieveAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    lookup_field = 'slug'

# ----------------------
# CART FUNCTIONALITY
# ----------------------

def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    # Get existing cart from session or create new one
    cart = request.session.get('cart', {})

    # Add or update quantity
    product_id_str = str(product_id)
    if product_id_str in cart:
        cart[product_id_str] += 1
    else:
        cart[product_id_str] = 1

    # Save cart back into session
    request.session['cart'] = cart
    request.session.modified = True

    # Redirect back to product detail page
    messages.success(request, f'Added {product.name} to cart.')
    return redirect('product_detail_page', slug=product.slug)
