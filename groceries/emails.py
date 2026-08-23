from config.email import send_transactional_email


def send_grocery_order_email(order, status_update=False):
    if not order.user.email:
        return False
    subject = f"ZIYAMART grocery order #{order.pk}: {order.get_status_display()}"
    intro = "Your grocery order was updated" if status_update else "Your grocery order was placed"
    return send_transactional_email(
        to_email=order.user.email,
        to_name=order.full_name,
        subject=subject,
        text_content=(
            f"Hello {order.full_name},\n\n{intro}.\n"
            f"Store: {order.store.name}\nStatus: {order.get_status_display()}\n"
            f"Total: Rs. {order.total}\nDelivery: {order.get_delivery_mode_display()}\n\n"
            "Thank you for shopping with ZIYAMART."
        ),
    )
