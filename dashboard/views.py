import json
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from django.utils.text import slugify
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.utils import timezone
from orders.models import (
    Order, 
    OrderItem,
    ReturnRequest,
    SupportTicket,
    SupportReply,
    OrderTimeline,
    )
from products.models import (
    Product,
    Category,
    ProductImage,
    SubCategory,
    ProductColor,
    ProductVariant,
)
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from products.models import ProductReview
from orders.models import ReturnRequest, SupportTicket
from django.db.models import Q
from django.template.loader import render_to_string
from django.contrib import messages
from django.http import HttpResponse
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from django.db import transaction
from products.models import ProductVariant
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth

# ✅ Only allow superusers (admins) to access dashboard
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def admin_dashboard(request):
    total_orders = Order.objects.count()
    total_revenue = (
        Order.objects.filter(status="Paid")
        .aggregate(Sum("total_price"))["total_price__sum"]
        or 0
    )
    pending_orders = Order.objects.filter(status="Pending").count()
    top_products = (
        OrderItem.objects.values("product__name")
        .annotate(total=Sum("quantity"))
        .order_by("-total")[:5]
    )

    products = Product.objects.all()
    categories = Category.objects.all()
    subcategories = SubCategory.objects.all()

    context = {
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "pending_orders": pending_orders,
        "top_products": top_products,
        "products": products,
        "categories": categories,
        "subcategories": subcategories,
    }
    return render(request, "dashboard/admin_dashboard.html", context)


# ✅ Local Orders page
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def local_orders_list(request):
    local_orders = (
        Order.objects.filter(pincode="243638")
        .exclude(status="Pending")
        .order_by("-created_at")
    )
    return render(request, "dashboard/local_orders.html", {"local_orders": local_orders})


# ✅ Shipping Orders page
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def shipping_orders_list(request):
    shipping_orders = (
        Order.objects.exclude(pincode="243638")
        .exclude(status="Pending")
        .order_by("-created_at")
    )
    return render(request, "dashboard/shipping_orders.html", {"shipping_orders": shipping_orders})


# ✅ Mark order as shipped
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def mark_order_shipped(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == "POST":
        order.status = "Shipped"
        order.save()
    return redirect(request.META.get("HTTP_REFERER", "admin_dashboard"))


# ✅ Add Category
def add_category(request):
    if request.method == "POST":
        name = request.POST.get("name")
        Category.objects.create(name=name, slug=slugify(name))
        return redirect("admin_dashboard")
    return render(request, "dashboard/add_category.html")


# ✅ Delete Category
def delete_category(request, id):
    category = get_object_or_404(Category, id=id)
    if request.method == "POST":
        category.delete()
        return redirect("admin_dashboard")
    return render(request, "dashboard/confirm_delete_category.html", {"category": category})


# ✅ Add SubCategory
def add_subcategory(request):
    categories = Category.objects.all()
    if request.method == "POST":
        name = request.POST.get("name")
        category_id = request.POST.get("category")
        category = get_object_or_404(Category, id=category_id)
        SubCategory.objects.create(name=name, category=category)
        return redirect("admin_dashboard")
    return render(request, "dashboard/add_subcategory.html", {"categories": categories})


# ✅ Delete SubCategory
def delete_subcategory(request, id):
    subcategory = get_object_or_404(SubCategory, id=id)
    if request.method == "POST":
        subcategory.delete()
        return redirect("admin_dashboard")
    return render(request, "dashboard/confirm_delete_subcategory.html", {"subcategory": subcategory})



@transaction.atomic
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def add_product(request):

    categories = Category.objects.all().order_by("name")

    subcategories = (
        SubCategory.objects
        .select_related("category")
        .order_by("name")
    )

    # -----------------------------
    # SHOW FORM
    # -----------------------------
    if request.method != "POST":

        return render(
            request,
            "dashboard/add_product.html",
            {
                "categories": categories,
                "subcategories": subcategories,
            },
        )

    # -----------------------------
    # BASIC PRODUCT DATA
    # -----------------------------

    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "").strip()
    category_id = request.POST.get("category")
    subcategory_id = request.POST.get("subcategory")
    product_type = request.POST.get("product_type")
    cover_image = request.FILES.get("image")

    # -----------------------------
    # PRICE
    # -----------------------------

    try:
        price = float(request.POST.get("price", 0))
    except (ValueError, TypeError):

        messages.error(
            request,
            "Please enter a valid product price."
        )

        return redirect("add_product")

    # -----------------------------
    # STOCK
    # -----------------------------

    try:
        stock = int(request.POST.get("stock", 0))
    except (ValueError, TypeError):

        stock = 0

    # -----------------------------
    # VALIDATION
    # -----------------------------

    if not name:

        messages.error(
            request,
            "Product name is required."
        )

        return redirect("add_product")

    if not category_id:

        messages.error(
            request,
            "Please select a category."
        )

        return redirect("add_product")

    category = get_object_or_404(
        Category,
        id=category_id
    )

    subcategory = None

    if subcategory_id:

        subcategory = get_object_or_404(
            SubCategory,
            id=subcategory_id
        )

    # -----------------------------
    # SIZES
    # -----------------------------

    sizes = []

    for size in request.POST.getlist("sizes[]"):

        size = size.strip()

        if size:

            sizes.append(size)

    if not sizes:

        messages.error(
            request,
            "Please add at least one size."
        )

        return redirect("add_product")

    # -----------------------------
    # COLORS
    # -----------------------------

    color_names = request.POST.getlist("color_name[]")
    color_hexes = request.POST.getlist("color_hex[]")

    valid_colors = []

    for index, color_name in enumerate(color_names):

        color_name = color_name.strip()

        if not color_name:
            continue

        valid_colors.append({
            "name": color_name,
            "hex": (
                color_hexes[index]
                if index < len(color_hexes)
                else "#000000"
            ),
            "index": index,
        })

    if not valid_colors:

        messages.error(
            request,
            "Please add at least one color."
        )

        return redirect("add_product")

    # -----------------------------
    # CREATE PRODUCT
    # -----------------------------

    product = Product.objects.create(
        name=name,
        description=description,
        price=price,
        stock=stock,
        category=category,
        subcategory=subcategory,
        product_type=product_type,
        available_sizes=sizes,
        image=cover_image,
        is_active=True,
    )

    # -----------------------------
    # CONTINUE IN PART 2
    # -----------------------------
        # -----------------------------
    # CREATE COLORS
    # -----------------------------

    created_colors = []

    for display_order, color_data in enumerate(valid_colors):

        color = ProductColor.objects.create(
            product=product,
            name=color_data["name"],
            hex_code=color_data["hex"],
            display_order=display_order,
        )

        created_colors.append(color)

        # -----------------------------
        # GALLERY IMAGES
        # -----------------------------

        gallery_images = request.FILES.getlist(
            f"color_gallery_{color_data['index']}"
        )

        first_image = None

        for image_order, image in enumerate(gallery_images):

            product_image = ProductImage.objects.create(
                product=product,
                color=color,
                image=image,
                display_order=image_order,
            )

            if image_order == 0:
                first_image = product_image.image

        # Set first gallery image as color image

        if first_image:

            color.image = first_image
            color.save(update_fields=["image"])

    # -----------------------------
    # CREATE VARIANTS
    # -----------------------------

    stocks = request.POST.getlist("stocks[]")

    for color in created_colors:

        for size_index, size in enumerate(sizes):

            try:
                variant_stock = int(stocks[size_index])

            except (IndexError, ValueError, TypeError):

                variant_stock = 0

            ProductVariant.objects.create(
                product=product,
                color=color,
                size=size,
                stock=variant_stock,
                is_active=True,
            )

    # -----------------------------
    # SUCCESS
    # -----------------------------

    messages.success(
        request,
        f'"{product.name}" added successfully.'
    )

    return redirect("products_management")

# ✅ Delete Product
@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def delete_product(request, id):

    product = get_object_or_404(Product, id=id)

    if request.method == "POST":

        if OrderItem.objects.filter(product=product).exists():
            messages.error(
                request,
                f'"{product.name}" cannot be deleted because it has been ordered.'
            )
            return redirect("products_management")

        product.delete()

        messages.success(
            request,
            f'"{product.name}" deleted successfully.'
        )

        return redirect("products_management")

    return render(
        request,
        "dashboard/confirm_delete_product.html",
        {
            "product": product,
        },
    )

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def toggle_product_status(request, id):

    product = get_object_or_404(Product, id=id)

    product.is_active = not product.is_active
    product.save()

    if product.is_active:
        messages.success(
            request,
            f"{product.name} has been activated."
        )
    else:
        messages.success(
            request,
            f"{product.name} has been deactivated."
        )

    return redirect("products_management")


@csrf_exempt
def ajax_add_category(request):

    if request.method == "POST":

        data = json.loads(request.body)

        name = data.get("name", "").strip()

        if not name:
            return JsonResponse({
                "success": False
            })

        category, created = Category.objects.get_or_create(
            name=name,
            defaults={
                "slug": slugify(name)
            }
        )

        return JsonResponse({
            "success": True,
            "id": category.id,
            "name": category.name
        })

    return JsonResponse({
        "success": False
    })


@csrf_exempt
def ajax_add_subcategory(request):

    if request.method == "POST":

        data = json.loads(request.body)

        name = data.get("name", "").strip()

        category_id = data.get("category")

        if not name or not category_id:

            return JsonResponse({
                "success": False
            })

        category = get_object_or_404(
            Category,
            id=category_id
        )

        subcategory, created = SubCategory.objects.get_or_create(
            name=name,
            category=category
        )

        return JsonResponse({

            "success": True,

            "id": subcategory.id,

            "name": subcategory.name

        })

    return JsonResponse({

        "success": False

    })



@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def products_management(request):

    products = (
        Product.objects
        .select_related("category", "subcategory")
        .order_by("-created")
    )

    return render(
        request,
        "dashboard/products_management.html",
        {
            "products": products,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def categories_management(request):

    categories = Category.objects.all()

    return render(
        request,
        "dashboard/categories_management.html",
        {
            "categories": categories,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def subcategories_management(request):

    subcategories = (
        SubCategory.objects
        .select_related("category")
    )

    return render(
        request,
        "dashboard/subcategories_management.html",
        {
            "subcategories": subcategories,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def inventory_management(request):

    variants = (
        ProductVariant.objects
        .select_related("product", "color")
        .order_by("product__name")
    )

    return render(
        request,
        "dashboard/inventory_management.html",
        {
            "variants": variants,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def customers_management(request):

    customers = (
        User.objects
        .filter(is_superuser=False)
        .order_by("-date_joined")
    )

    return render(
        request,
        "dashboard/customers_management.html",
        {
            "customers": customers,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def reviews_management(request):

    reviews = (
        ProductReview.objects
        .select_related("user", "product")
        .order_by("-created_at")
    )

    return render(
        request,
        "dashboard/reviews_management.html",
        {
            "reviews": reviews,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def returns_management(request):

    returns = (
        ReturnRequest.objects
        .select_related(
            "user",
            "order",
            "order_item",
        )
        .order_by("-created_at")
    )

    search = request.GET.get("search")
    status = request.GET.get("status")
    refund = request.GET.get("refund")

    if search:

        returns = returns.filter(

            Q(id__icontains=search) |

            Q(order__id__icontains=search) |

            Q(user__username__icontains=search) |

            Q(user__email__icontains=search) |

            Q(order_item__product_name__icontains=search)

        )

    if status:

        returns = returns.filter(status=status)

    if refund:

        returns = returns.filter(refund_status=refund)

    # -------------------------
    # Pagination
    # -------------------------

    paginator = Paginator(returns, 10)

    page_number = request.GET.get("page")

    returns = paginator.get_page(page_number)

    context = {

        "returns": returns,

        "total_requests": ReturnRequest.objects.count(),

        "pending_requests": ReturnRequest.objects.filter(
            status="Pending"
        ).count(),

        "approved_requests": ReturnRequest.objects.filter(
            status="Approved"
        ).count(),

        "rejected_requests": ReturnRequest.objects.filter(
            status="Rejected"
        ).count(),

        "refund_pending": ReturnRequest.objects.filter(
            refund_status="Pending"
        ).count(),

        "refund_processed": ReturnRequest.objects.filter(
            refund_status="Processed"
        ).count(),
    }

    return render(
        request,
        "dashboard/returns_management.html",
        context,
    )

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def support_management(request):

    tickets = (
        SupportTicket.objects
        .select_related("user", "user__profile", "order")
        .order_by("-created_at")
    )

    # -------------------------
    # Search
    # -------------------------

    search = request.GET.get("search", "").strip()

    if search:

        tickets = tickets.filter(

            Q(id__icontains=search) |

            Q(subject__icontains=search) |

            Q(message__icontains=search) |

            Q(user__username__icontains=search) |

            Q(user__first_name__icontains=search) |

            Q(user__last_name__icontains=search) |

            Q(user__email__icontains=search) |

            Q(order__id__icontains=search)

        )

    # -------------------------
    # Status Filter
    # -------------------------

    status = request.GET.get("status", "").strip()

    if status:

        tickets = tickets.filter(status=status)

    # -------------------------
    # Read Filter
    # -------------------------

    read = request.GET.get("read", "").strip()

    if read == "Unread":

        tickets = tickets.filter(is_read=False)

    elif read == "Read":

        tickets = tickets.filter(is_read=True)

    # -------------------------
    # Pagination
    # -------------------------

    paginator = Paginator(tickets, 10)

    page_number = request.GET.get("page")

    tickets = paginator.get_page(page_number)

    context = {

        "tickets": tickets,

        "search": search,

        "selected_status": status,

        "selected_read": read,

        # Summary Cards

        "total_tickets": SupportTicket.objects.count(),

        "open_tickets": SupportTicket.objects.filter(
            status="Open"
        ).count(),

        "progress_tickets": SupportTicket.objects.filter(
            status="In Progress"
        ).count(),

        "resolved_tickets": SupportTicket.objects.filter(
            status="Resolved"
        ).count(),

        "unread_tickets": SupportTicket.objects.filter(
            is_read=False
        ).count(),

    }

    return render(
        request,
        "dashboard/support_management.html",
        context,
    )

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def analytics_dashboard(request):

    monthly_sales = list(
        Order.objects.filter(payment_status="Paid")
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("total_price"))
        .order_by("month")
    )

    top_products = (
        OrderItem.objects
        .values("product_name")
        .annotate(quantity=Sum("quantity"))
        .order_by("-quantity")[:5]
    )

    latest_orders = (
        Order.objects
        .select_related("user")
        .order_by("-created_at")[:10]
    )

    context = {

        "total_orders": Order.objects.count(),

        "total_revenue":
            Order.objects.filter(payment_status="Paid")
            .aggregate(total=Sum("total_price"))["total"] or 0,

        "total_customers":
            User.objects.filter(is_superuser=False).count(),

        "total_products":
            Product.objects.count(),

        "pending_orders":
            Order.objects.filter(status="Pending").count(),

        "processing_orders":
            Order.objects.filter(status="Processing").count(),

        "packed_orders":
            Order.objects.filter(status="Packed").count(),

        "shipped_orders":
            Order.objects.filter(status="Shipped").count(),

        "delivered_orders":
            Order.objects.filter(status="Delivered").count(),

        "cancelled_orders":
            Order.objects.filter(status="Cancelled").count(),

        "returned_orders":
            Order.objects.filter(status="Returned").count(),

        "monthly_sales": monthly_sales,

        "top_products": top_products,

        "latest_orders": latest_orders,
    }

    return render(
        request,
        "dashboard/analytics_dashboard.html",
        context,
    )

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def order_management(request):

    orders = (
        Order.objects
        .select_related("user")
        .prefetch_related("items")
        .order_by("-created_at")
    )

    # Search
    search = request.GET.get("search", "").strip()

    if search:
        orders = orders.filter(
            Q(id__icontains=search) |
            Q(full_name__icontains=search) |
            Q(phone__icontains=search) |
            Q(city__icontains=search) |
            Q(user__username__icontains=search)
        )

    # Order Status Filter
    status = request.GET.get("status", "").strip()

    if status:
        orders = orders.filter(status=status)

    # Payment Status Filter
    payment = request.GET.get("payment", "").strip()

    if payment:
        orders = orders.filter(payment_status=payment)



    today = timezone.localdate()

    context = {
        "orders": orders,

        "search": search,
        "selected_status": status,
        "selected_payment": payment,

        # Main Statistics
        "total_orders": Order.objects.count(),

        "new_orders": Order.objects.filter(
            is_new=True
        ).count(),

        "pending": Order.objects.filter(
            status="Pending"
        ).count(),

        "processing": Order.objects.filter(
            status="Processing"
        ).count(),

        "packed": Order.objects.filter(
            status="Packed"
        ).count(),

        "shipped": Order.objects.filter(
            status="Shipped"
        ).count(),

        "out_for_delivery": Order.objects.filter(
            status="Out for Delivery"
        ).count(),

        "delivered": Order.objects.filter(
            status="Delivered"
        ).count(),

        "cancelled": Order.objects.filter(
            status="Cancelled"
        ).count(),

        "returned": Order.objects.filter(
            status="Returned"
        ).count(),

        # Today's Activity
        "today_orders": Order.objects.filter(
            created_at__date=today
        ).count(),

        "today_revenue": (
            Order.objects.filter(
                created_at__date=today,
                payment_status="Paid"
            ).aggregate(
                total=Sum("total_price")
            )["total"] or 0
        ),

        # Orders Needing Action
        "action_required": Order.objects.filter(
            status__in=[
                "Pending",
                "Processing",
                "Packed",
            ]
        ).count(),

        # High Value Orders
        "high_value_orders": Order.objects.filter(
            total_price__gte=5000
        ).count(),
    }
    return render(
    request,
    "dashboard/orders_management.html",
    context,
)

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def order_detail_ajax(request, order_id):

    order = get_object_or_404(
        Order.objects.select_related("user")
        .prefetch_related(
            "items",
            "items__product",
            "items__variant",
        ),
        id=order_id,
    )

    html = render_to_string(
        "dashboard/includes/order_detail_modal.html",
        {
            "order": order,
        },
        request=request,
    )

    return JsonResponse({
        "html": html
    })


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def update_order_status(request, order_id):

    order = get_object_or_404(Order, id=order_id)

    if request.method == "POST":

        new_status = request.POST.get("status")
        payment_status = request.POST.get("payment_status")
        old_status = order.status

        valid_flow = {
            "Pending": ["Processing", "Cancelled"],
            "Processing": ["Packed", "Cancelled"],
            "Packed": ["Shipped", "Cancelled"],
            "Shipped": ["Out for Delivery"],
            "Out for Delivery": ["Delivered"],
            "Delivered": ["Returned"],
            "Cancelled": [],
            "Returned": [],
        }

                # Remove NEW badge after first admin action
        if order.is_new:
            order.is_new = False

        if (
            order.status == "Pending"
            and new_status == "Processing"
        ):
            order.confirmed_at = timezone.now()
            order.confirmed_by = request.user

        elif (
            order.status == "Processing"
            and new_status == "Packed"
        ):
            order.packed_at = timezone.now()

        elif (
            order.status == "Packed"
            and new_status == "Shipped"
        ):
            order.shipped_at = timezone.now()

        elif (
            order.status == "Shipped"
            and new_status == "Out for Delivery"
        ):
            order.out_for_delivery_at = timezone.now()

        elif (
            order.status == "Out for Delivery"
            and new_status == "Delivered"
        ):
            order.delivered_at = timezone.now()

        elif new_status == "Cancelled":
            order.cancelled_at = timezone.now()
        order.status = new_status
        order.payment_status = payment_status

        order.save()

    # -------------------------------
    # ORDER TIMELINE
    # -------------------------------

    if old_status != new_status:

        event_map = {
            "Processing": "Order Confirmed",
            "Packed": "Packed",
            "Shipped": "Shipped",
            "Out for Delivery": "Out for Delivery",
            "Delivered": "Delivered",
            "Cancelled": "Cancelled",
            "Returned": "Returned",
        }

        OrderTimeline.objects.create(
            order=order,
            event=event_map.get(new_status, new_status),
            description=f"Order status changed from {old_status} to {new_status}.",
            performed_by=request.user,
        )       

        messages.success(
            request,
            "Order updated successfully."
        )

    return redirect("orders_management")

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def download_invoice(request, order_id):

    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        id=order_id
    )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Invoice-{order.id}.pdf"'

    doc = SimpleDocTemplate(response)
    styles = getSampleStyleSheet()

    elements = []

    elements.append(Paragraph("<b>ZIYA FASHION</b>", styles["Title"]))
    elements.append(Paragraph(f"Invoice #{order.id}", styles["Heading2"]))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    elements.append(Paragraph(f"<b>Customer:</b> {order.full_name}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Phone:</b> {order.phone}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Address:</b> {order.address}", styles["Normal"]))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    data = [["Product", "Qty", "Price", "Total"]]

    for item in order.items.all():

        data.append([
            item.product_name,
            item.quantity,
            f"₹{item.price}",
            f"₹{item.price * item.quantity}"
        ])

    data.append(["", "", "Grand Total", f"₹{order.total_price}"])

    table = Table(data, colWidths=[3*inch, .8*inch, 1*inch, 1.2*inch])

    table.setStyle(TableStyle([

        ("BACKGROUND",(0,0),(-1,0),colors.black),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("GRID",(0,0),(-1,-1),1,colors.grey),
        ("BACKGROUND",(0,1),(-1,-1),colors.beige),
        ("BOTTOMPADDING",(0,0),(-1,0),10),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),

    ]))

    elements.append(table)

    doc.build(elements)

    return response
from django.utils.text import slugify

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def edit_product(request, id):

    product = get_object_or_404(Product, id=id)

    categories = Category.objects.all()
    subcategories = SubCategory.objects.all()

    if request.method == "POST":

        old_name = product.name

        product.name = request.POST.get("name", "").strip()
        product.description = request.POST.get("description", "").strip()
        product.price = request.POST.get("price")
        product.stock = request.POST.get("stock")

        product.category = get_object_or_404(
            Category,
            id=request.POST.get("category")
        )

        subcategory_id = request.POST.get("subcategory")

        if subcategory_id:
            product.subcategory = get_object_or_404(
                SubCategory,
                id=subcategory_id
            )
        else:
            product.subcategory = None

        product.product_type = request.POST.get("product_type")

        # Only regenerate the slug if the product name changed
        if product.name != old_name:

            base_slug = slugify(product.name)
            slug = base_slug
            counter = 1

            while Product.objects.filter(slug=slug).exclude(id=product.id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            product.slug = slug

        if request.FILES.get("image"):
            product.image = request.FILES["image"]

        product.save()

        messages.success(
            request,
            "Product updated successfully."
        )

        return redirect("products_management")

    return render(
        request,
        "dashboard/edit_product.html",
        {
            "product": product,
            "categories": categories,
            "subcategories": subcategories,
        },
    )

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def edit_inventory(request, id):

    variant = get_object_or_404(
        ProductVariant,
        id=id
    )

    if request.method == "POST":

        variant.stock = request.POST.get("stock")

        variant.sku = request.POST.get("sku")

        variant.is_active = (
            True if request.POST.get("is_active") else False
        )

        variant.save()


        messages.success(
            request,
            "Inventory updated successfully."
        )

        return redirect(
            "inventory_management"
        )


    return render(
        request,
        "dashboard/edit_inventory.html",
        {
            "variant": variant
        }
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def approve_review(request, id):

    review = get_object_or_404(ProductReview, id=id)

    review.is_approved = True
    review.save()

    messages.success(
        request,
        "Review approved successfully."
    )

    return redirect("reviews_management")


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def delete_review(request, id):

    review = get_object_or_404(ProductReview, id=id)

    review.delete()

    messages.success(
        request,
        "Review deleted successfully."
    )

    return redirect("reviews_management")

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
@transaction.atomic
def approve_return(request, return_id):

    return_request = get_object_or_404(
        ReturnRequest,
        id=return_id
    )

    # Prevent processing the same request twice
    if return_request.status != "Pending":

        messages.warning(
            request,
            "This return request has already been processed."
        )

        return redirect("returns_management")

    if request.method == "POST":

        # -------------------------
        # Update Return Request
        # -------------------------

        return_request.status = "Approved"

        return_request.admin_note = request.POST.get(
            "admin_note",
            ""
        )

        return_request.refund_status = request.POST.get(
            "refund_status",
            "Pending"
        )

        return_request.save()

        # -------------------------
        # Restock Only Returned Item
        # -------------------------

        returned_item = return_request.order_item

        if returned_item:

            if returned_item.variant:

                returned_item.variant.stock += returned_item.quantity
                returned_item.variant.save()

            elif returned_item.product:

                returned_item.product.stock += returned_item.quantity
                returned_item.product.save()

        # -------------------------
        # Update Order Status
        # -------------------------

        order = return_request.order

        total_items = order.items.count()

        approved_returns = ReturnRequest.objects.filter(
            order=order,
            status="Approved"
        ).count()

        if total_items > 0 and approved_returns >= total_items:

            order.status = "Returned"
            order.save()

        messages.success(
            request,
            "Return approved and inventory updated."
        )

    return redirect("returns_management")

@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def reject_return(request, return_id):

    return_request = get_object_or_404(
        ReturnRequest,
        id=return_id
    )

    if request.method == "POST":

        return_request.status = "Rejected"

        return_request.admin_note = request.POST.get(
            "admin_note",
            ""
        )

        return_request.refund_status = "Rejected"

        return_request.save()

        messages.success(
            request,
            "Return request rejected."
        )

    return redirect("returns_management")


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def support_ticket_detail(request, ticket_id):

    ticket = get_object_or_404(
        SupportTicket.objects.select_related(
            "user",
            "order",
        ),
        id=ticket_id,
    )

    replies = (
        ticket.replies
        .select_related("user")
        .all()
    )

    if not ticket.is_read:
        ticket.is_read = True
        ticket.save(update_fields=["is_read"])

    return render(
        request,
        "dashboard/support_ticket_detail.html",
        {
            "ticket": ticket,
            "replies": replies,
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def reply_support_ticket(request, ticket_id):

    ticket = get_object_or_404(
        SupportTicket,
        id=ticket_id,
    )

    if request.method == "POST":

        message = request.POST.get("message", "").strip()

        if message:

            SupportReply.objects.create(
                ticket=ticket,
                user=request.user,
                message=message,
                is_staff=True,
            )

            ticket.last_reply_at = timezone.now()
            ticket.status = "In Progress"
            ticket.save()

            messages.success(
                request,
                "Reply sent successfully."
            )

            # Email notification will be added later.

    return redirect(
        "support_ticket_detail",
        ticket_id=ticket.id,
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/admin/login/")
def update_support_status(request, ticket_id):

    ticket = get_object_or_404(
        SupportTicket,
        id=ticket_id,
    )

    if request.method == "POST":

        ticket.status = request.POST.get(
            "status",
            ticket.status,
        )

        ticket.admin_note = request.POST.get(
            "admin_note",
            "",
        )

        ticket.save()

        messages.success(
            request,
            "Ticket updated successfully."
        )

    return redirect(
        "support_ticket_detail",
        ticket_id=ticket.id,
    )