from django.core.mail import send_mail
from django.conf import settings


def send_order_email(order, subject, message):

    if not order.user.email:
        return

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.user.email],
        fail_silently=False,
    )