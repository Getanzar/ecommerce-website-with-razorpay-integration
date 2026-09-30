declare module "react-native-razorpay" {
  const checkout: { open(options: { key: string; order_id: string; amount: number; currency: string; name: string; description?: string; theme?: { color: string } }): Promise<{ razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string }> };
  export default checkout;
}
