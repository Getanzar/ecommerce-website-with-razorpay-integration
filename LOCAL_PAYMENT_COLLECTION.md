# Local Delivery Payment Collection

Applies to grocery, food, and merchandise deliveries handled by local agents.

- Run `python manage.py migrate --noinput` during deployment.
- Enable UPI QR Codes on the ZIYAMART Razorpay account. Existing Razorpay key
  settings are used; no personal agent UPI account is accepted.
- Enable `qr_code.credited` on the existing signed Razorpay webhook endpoint.
  The agent's Check payment status button also verifies capture directly.
- Release an updated mobile build for the Cash and Pay online controls.

Cash received marks the customer's collection paid, while CODRemittance keeps
the amount owed by the agent to ZIYAMART. Agent earnings and seller payouts remain
blocked until outstanding cash is remitted. QR capture creates an online payment
transaction and no cash remittance. Each shipment has its own collection amount;
an entire parcel order is paid only once its required total has been collected.

QR creation uses a fixed amount and single use. A network timeout can leave an
issuing record: do not repeat collection until it is reconciled. Find the QR in
the Razorpay dashboard by its delivery_id note, then run:

```powershell
python manage.py reconcile_delivery_qr --delivery-id 123 --qr-id qr_FROM_RAZORPAY
```

The command verifies the QR's delivery, amount, and usage before attaching it.
Switching from an existing QR to cash requires successful QR closure and a fresh
payment check. Authorized payments block cash collection until capture resolves.

Existing completed cash deliveries retain their COD remittance records. Existing
mobile builds can still explicitly confirm cash with delivery completion; new
builds use the separate payment collection step. Delivery-code verification
remains required for completion after payment.
