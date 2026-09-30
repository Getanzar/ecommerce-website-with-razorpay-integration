import { request } from "./api";

export type Kind = "shop" | "food" | "grocery";
export type SellerSubcategory = {
  id: number;
  name: string;
};

export type SellerCategory = {
  id: number;
  name: string;
  slug: string;
  subcategories: SellerSubcategory[];
};

export type SellerCategoriesResponse = {
  categories: SellerCategory[];
};
export type Role = { name: string; status: string; payouts_enabled: boolean; is_online?: boolean; pincode?: string };
export type Roles = { seller: Role | null; rider: Role | null };
export type Page<T> = { count: number; next: string | null; results: T[] };
export type Workspace = { name: string; business_category: string; allowed_kinds: Kind[]; stores: { kind: Kind; name: string; accepts_orders: boolean }[]; payouts_enabled: boolean; bank_last4: string; return_balance: string };
export type SellerOrder = { id: number; order_id: number; kind: Kind; status: string; payment_status: string; payment_method: string; customer: string; address: string; amount: string; next_status: string | null; can_cancel: boolean; created_at: string; courier: string; tracking_number: string; items: { name: string; quantity: number; variant: string }[] };
export type Listing = { id: number; name: string; active: boolean; moderation: string | null; rejection_reason: string; variants: { id: number; name: string; stock: number | null; price: string }[] };
export type Payout = { id: number; order_id?: number; delivery_id?: number; amount: string; gross?: string; fee?: string; status: string; scheduled_for: string | null; failure_reason: string };
export type Job = { id: number; kind: string; status: string; pickup_name: string; pickup_address: string; pincode: string; customer_name: string; customer_phone: string; delivery_address: string; payment_method: string; collection_amount: string; gross: string; fee: string; net: string; next_status: string | null; location_updated_at: string | null };
export const partnerRequest = <T,>(token: string, path: string, method = "GET", data?: unknown) =>
  request<T>(`/partners/${path}`, { method, ...(data === undefined ? {} : { body: JSON.stringify(data) }) }, token);
