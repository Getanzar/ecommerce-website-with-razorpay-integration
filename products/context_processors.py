from .models import Category
from .catalog import in_stock_products

def categories_processor(request):
    return {
        "categories": Category.objects.filter(products__in=in_stock_products()).distinct()
    }
