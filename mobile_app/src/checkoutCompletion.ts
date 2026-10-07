import { PayableOrder, payOrder } from "./nativePayments";

/** A saved order must reach payment even when the cart refresh is unavailable. */
export async function completePlacedOrder<T extends PayableOrder>(
  token: string,
  order: T,
  refreshCart: () => Promise<void> | void,
): Promise<PayableOrder> {
  try {
    return order.payment_method === "online" ? await payOrder(token, order) : order;
  } finally {
    // Checkout has already reserved the order and emptied its server-side cart.
    // A refresh failure must not hide payment success or replace its recovery error.
    try { await refreshCart(); } catch { /* Refresh again when the bag is reopened. */ }
  }
}
