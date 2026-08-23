from config.email import send_transactional_email


def send_order_email(order, subject, message):

    if not order.user.email:
        return False

    return send_transactional_email(
        to_email=order.user.email,
        to_name=order.full_name or order.user.get_full_name(),
        subject=subject,
        text_content=message,
    )


def send_order_confirmation_email(order):
    payment_label = "paid online" if order.payment_status == "Paid" else "Cash on Delivery"
    return send_order_email(
        order,
        f"ZIYAMART order #{order.id} confirmed",
        (
            f"Hello {order.full_name},\n\n"
            f"We received your order #{order.id} for Rs. {order.total_price}. "
            f"Payment: {payment_label}. Current status: {order.status}.\n\n"
            "Thank you for shopping with ZIYAMART."
        ),
    )


def send_order_status_email(order, old_status):
    return send_order_email(
        order,
        f"ZIYAMART order #{order.id}: {order.status}",
        (
            f"Hello {order.full_name},\n\n"
            f"Your order #{order.id} changed from {old_status} to {order.status}.\n\n"
            "Thank you for shopping with ZIYAMART."
        ),
    )
