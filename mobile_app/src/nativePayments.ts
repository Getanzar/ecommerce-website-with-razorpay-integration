import Constants from "expo-constants";
import { request } from "./api";

export type PayableOrder = { id: number; kind: string; payment_method: string; payment_status: string; razorpay?: { key_id: string; order_id: string; amount: number; currency: string; name: string } };

export async function recoverPayment(token: string, kind: string, id: number): Promise<PayableOrder> {
  return request(`/orders/${kind}/${id}/payment/`, { method: "POST", body: JSON.stringify({ action: "recover" }) }, token);
}

export async function payOrder(token: string, order: PayableOrder): Promise<PayableOrder> {
  if (order.payment_status === "Paid" || order.payment_method === "cod") return order;
  if (Constants?.appOwnership === "expo") {
    throw new Error("Online payment requires an installed development or release build. Expo Go supports browsing, but does not include Razorpay.");
  }
  const current = await recoverPayment(token, order.kind, order.id);
  if (current.payment_status === "Paid") return current;
  if (!current.razorpay) throw new Error("This order cannot accept payment. Refresh your orders or contact support.");
  const path = `/orders/${order.kind}/${order.id}/payment/`;
  let result;
  try {
    const { key_id, ...options } = current.razorpay;
    const { default: RazorpayCheckout } = await import("react-native-razorpay");
    result = await RazorpayCheckout.open({ ...options, key: key_id, description: `Order #${order.id}`, theme: { color: "#C84E1F" } });
  } catch (error: any) {
    const recovered = await recoverPayment(token, order.kind, order.id).catch(() => null);
    if (recovered?.payment_status === "Paid") return recovered;
    await request(path, { method: "POST", body: JSON.stringify({ action: error?.code === 2 ? "cancelled" : "failed" }) }, token).catch(() => undefined);
    throw new Error(`Payment was not confirmed. Order #${order.id} is saved. Open Orders to check payment or retry.`);
  }
  try {
    const verified = await request<PayableOrder>(path, { method: "POST", body: JSON.stringify({ action: "verify", ...result }) }, token);
    if (verified.payment_status !== "Paid") throw new Error("Capture pending");
    return verified;
  } catch {
    throw new Error(`Payment confirmation is pending for order #${order.id}. Check payment in Orders before trying again.`);
  }
}
