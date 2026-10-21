from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from payments.models import SellerDeliveryCharge
from .models import Order


class CustomerTrackingDisplayTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user('tracking-customer')
        self.client.force_login(self.customer)
        self.order = Order.objects.create(
            user=self.customer, total_price='100.00', status='Processing',
            payment_method='online', payment_status='Paid',
        )
        self.url = reverse('order_detail', args=[self.order.pk])

    def test_seller_shipment_shows_tracking_and_paid_without_empty_message(self):
        SellerDeliveryCharge.objects.create(
            parcel_order=self.order, provider='delhivery',
            carrier_status='manifested', awb_number='55709410000022',
        )
        response = self.client.get(self.url)
        self.assertContains(response, 'Shipment booked — awaiting pickup')
        self.assertContains(response, 'Track AWB 55709410000022')
        self.assertContains(response, 'Payment status')
        self.assertContains(response, '<strong class="text-success">Paid</strong>', html=True)
        self.assertNotContains(response, 'Your shipment has not been created yet.')

    def test_empty_message_is_retained_when_no_shipment_exists(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Your shipment has not been created yet.')

    def test_legacy_tracking_is_retained_and_pending_payment_is_not_called_paid(self):
        self.order.awb_number = 'legacy-awb'
        self.order.payment_method = 'cod'
        self.order.payment_status = 'Pending'
        self.order.save()
        response = self.client.get(self.url)
        self.assertContains(response, '/track/package/legacy-awb')
        self.assertContains(response, '<strong>Pending</strong>', html=True)
        self.assertNotContains(response, 'Your shipment has not been created yet.')
