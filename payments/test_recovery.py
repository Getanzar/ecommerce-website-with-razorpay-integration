from io import StringIO
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from payments.models import PaymentTransaction


class ParcelPaymentRecoveryTests(TestCase):
    def setUp(self):
        self.payment = PaymentTransaction.objects.create(
            user=User.objects.create_user('recovery-customer'),
            provider='razorpay', channel_name='parcel',
            provider_order_id='order_recovery', amount='100.00',
        )
        self.entity = {'id': 'pay_recovery', 'order_id': 'order_recovery',
                       'status': 'captured', 'amount': 10000, 'currency': 'INR',
                       'amount_refunded': 0, 'refund_status': None}

    @patch('payments.management.commands.recover_parcel_payment.finalize_parcel_transaction')
    @patch('payments.management.commands.recover_parcel_payment.razorpay.Client')
    def test_inspection_does_not_create_order(self, client, finalize):
        client.return_value.order.payments.return_value = {'items': [self.entity]}
        call_command('recover_parcel_payment', 'order_recovery', stdout=StringIO())
        finalize.assert_not_called()

    @patch('payments.management.commands.recover_parcel_payment.finalize_parcel_transaction')
    @patch('payments.management.commands.recover_parcel_payment.razorpay.Client')
    def test_apply_requires_matching_unrefunded_capture(self, client, finalize):
        for changed in ({'amount': 9000}, {'currency': 'USD'}, {'amount_refunded': 10000},
                        {'refund_status': 'pending'}, {'order_id': 'other'}):
            client.return_value.order.payments.return_value = {'items': [{**self.entity, **changed}]}
            with self.assertRaises(CommandError):
                call_command('recover_parcel_payment', 'order_recovery', apply=True, stdout=StringIO())
        finalize.assert_not_called()

    @patch('payments.management.commands.recover_parcel_payment.finalize_parcel_transaction')
    @patch('payments.management.commands.recover_parcel_payment.razorpay.Client')
    def test_verified_capture_is_finalized(self, client, finalize):
        client.return_value.order.payments.return_value = {'items': [self.entity]}
        finalize.return_value = Mock(pk=42, payment_status='Paid')
        finalize.return_value.sellerdeliverycharges.all.return_value = []
        call_command('recover_parcel_payment', 'order_recovery', apply=True, stdout=StringIO())
        finalize.assert_called_once_with(self.payment, 'pay_recovery')
