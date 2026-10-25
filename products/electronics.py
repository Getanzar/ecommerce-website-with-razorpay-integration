"""Shared electronics taxonomy for the storefront and seller workspace."""
ELECTRONICS = {
    "mobile": {"name": "Mobiles", "icon": "phone", "fields": ["RAM", "Storage", "Processor", "Screen size", "Battery capacity", "Operating system", "Network support"]},
    "tv": {"name": "TVs", "icon": "tv", "fields": ["Screen size", "Resolution", "Display technology", "Smart TV platform", "Connectivity"]},
    "laptop": {"name": "Laptops", "icon": "laptop", "fields": ["Processor", "RAM", "Storage", "Screen size", "Operating system", "Graphics"]},
    "home_appliance": {"name": "Home Appliances", "icon": "house-gear", "fields": ["Appliance type", "Capacity", "Power consumption", "Energy rating", "Installation requirements"]},
    "mobile_accessory": {"name": "Mobile Accessories", "icon": "headphones", "fields": ["Accessory type", "Compatible devices", "Connector", "Material"]},
}

# Include existing merchandise categories without changing seller listings.
ELECTRONICS_ALIASES = {
    "mobile": ("mobile", "mobiles", "mobile phones", "smartphones"),
    "tv": ("tv", "tvs", "televisions", "television"),
    "laptop": ("laptop", "laptops"),
    "home_appliance": ("home appliances", "home appliance", "homeappliances"),
    "mobile_accessory": ("mobile accessories", "mobile accessory", "phone accessories", "phone covers", "phone cover", "mobile covers", "mobile cover"),
}

def catalog_icon(name):
    normalized = name.lower().strip().replace("-", "_").replace("_", " ")
    for kind, aliases in ELECTRONICS_ALIASES.items():
        if normalized in aliases:
            return ELECTRONICS[kind]["icon"]
    for words, icon in (( ("electronics",), "cpu"), (("shirt", "clothing", "fashion", "wear"), "person"), (("shoe", "footwear"), "bag"), (("clean", "bathroom"), "droplet"), (("beauty", "care"), "stars"), (("food", "grocery"), "basket"), (("accessor",), "handbag")):
        if any(word in normalized for word in words):
            return icon
    return "grid"


def electronics_filter(kind=None):
    from django.db.models import Q
    from django.utils.text import slugify
    kinds = [kind] if kind in ELECTRONICS else list(ELECTRONICS)
    query = Q(pk__in=[])
    if kind not in ELECTRONICS:
        query |= Q(category__slug="electronics")
    for key in kinds:
        query |= Q(product_type=key)
        for alias in ELECTRONICS_ALIASES[key]:
            query |= Q(category__slug=slugify(alias)) | Q(category__name__iexact=alias) | Q(subcategory__name__iexact=alias)
    return query
