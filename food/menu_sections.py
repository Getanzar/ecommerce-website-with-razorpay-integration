"""Standard sections available to every restaurant's menu editor."""

DEFAULT_MENU_SECTIONS = (
    "Starters", "Main Course", "Biryani", "Breads", "Desserts", "Beverages", "Drinks",
)


def ensure_menu_sections(restaurant):
    existing = {name.casefold() for name in restaurant.sections.values_list("name", flat=True)}
    for position, name in enumerate(DEFAULT_MENU_SECTIONS):
        if name.casefold() not in existing:
            restaurant.sections.get_or_create(name=name, defaults={"display_order": position})

