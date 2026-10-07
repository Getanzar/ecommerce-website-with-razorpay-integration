import { fetchWithRetry } from "./retry";
import { reportError } from "./telemetry";
import * as Device from "expo-device";
import { catalogPage } from "./catalogPaging";
import { assertSafeProductionApiUrl } from "./apiUrlSafety";
/**
 * Public API variables are commonly entered as a site origin. Keep that
 * configuration safe by normalising it to the versioned mobile API root.
 */
const configuredApiUrl = process.env.EXPO_PUBLIC_API_URL || "https://ziyamart.in/api/v1";
const isProductionBuild = process.env.EXPO_PUBLIC_APP_ENV === "production";
assertSafeProductionApiUrl(configuredApiUrl, isProductionBuild);
export const API_URL = `${configuredApiUrl.replace(/\/$/, "").replace(/\/api\/v1$/i, "")}/api/v1`;

export type User = {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  email_verified: boolean;
};
export type Category = {
  id: number;
  name: string;
  slug: string;
  image_url: string | null;
  background_image_url: string | null;
  subcategories: { id: number; name: string }[];
};
export type Color = {
  id: number;
  name: string;
  hex_code: string;
  image_url: string | null;
};
export type Variant = {
  id: number;
  color: Color;
  size: string;
  stock: number;
  price: string;
  image_url: string | null;
};
export type Product = {
  id: number;
  name: string;
  slug: string;
  description: string;
  price: string;
  image_url: string | null;
  category?: Category;
  rating?: number;
  review_count?: number;
  is_wishlisted?: boolean;
  seller_name?: string;
  variants?: Variant[];
  gallery?: string[];
  specifications?: Record<string, string>;
  reviews?: {
    id: number;
    username: string;
    rating: number;
    title: string;
    review: string;
    verified: boolean;
    created_at: string;
  }[];
};
export type CartItem = {
  id: number;
  product: Product;
  variant: Variant | null;
  quantity: number;
  total: string;
};
export type Cart = { items: CartItem[]; item_count: number; subtotal: string };
export type Address = {
  id: number;
  full_name: string;
  phone: string;
  address_line_1: string;
  address_line_2: string;
  city: string;
  state: string;
  pincode: string;
  address_type: string;
  is_default: boolean;
};
export type AuthResponse = { token: string; user: User };
export type SignupResponse = {
  message: string;
  email: string;
  debug_otp?: string;
};
export type MenuOption = { id: number; name: string; price: string };
export type MenuItem = {
  id: number;
  name: string;
  description: string;
  food_type: string;
  image_url: string | null;
  section: string;
  starting_price: string;
  options: MenuOption[];
};
export type Restaurant = {
  id: number;
  name: string;
  slug: string;
  description: string;
  cuisine: string;
  image_url: string | null;
  pincode: string;
  preparation_minutes: number;
  minimum_order: string;
  delivery_fee: string;
  accepts_orders: boolean;
  menu_items?: MenuItem[];
};
export type GroceryStore = {
  id: number;
  name: string;
  slug: string;
  description: string;
  image_url: string | null;
  address: string;
  pincode: string;
  phone: string;
  minimum_order: string;
  delivery_fee: string;
  estimated_delivery_minutes: number;
  accepts_orders: boolean;
};
export type GroceryProduct = {
  id: number;
  name: string;
  brand: string;
  image_url: string | null;
  unit: string;
  mrp: string;
  price: string;
  stock: number;
  is_perishable: boolean;
  store_name: string;
  category: {
    id: number;
    name: string;
    slug: string;
    image_url: string | null;
  };
};
export type FoodCartItem = {
  id: number;
  option_id: number;
  name: string;
  option_name: string;
  image_url: string | null;
  restaurant_id: number;
  restaurant_name: string;
  quantity: number;
  note: string;
  unit_price: string;
  total: string;
};
export type GroceryCartItem = {
  id: number;
  product_id: number;
  name: string;
  unit: string;
  image_url: string | null;
  store_id: number;
  store_name: string;
  stock: number;
  quantity: number;
  unit_price: string;
  total: string;
};
export type ServiceCart<T> = {
  items: T[];
  item_count: number;
  subtotal: string;
};
export type CheckoutQuote = {
  quote_id: string;
  expires_at: string;
  price: {
    kind: string;
    item_subtotal: string;
    delivery_charge: string;
    discount: string;
    total: string;
    tax_inclusive: boolean;
    delivery_mode: string;
    eta: string;
    source: string;
    cod_eligible: boolean;
    cod_unavailable_reason: string;
    address: { id: number; label: string };
  };
};
export type Order = {
  id: number;
  kind: "shop" | "food" | "grocery";
  created_at: string;
  updated_at: string;
  total_price: string;
  status: string;
  payment_method: string;
  payment_status: string;
  can_cancel: boolean;
  can_return: boolean;
  tracking_number: string;
  courier: string;
  care: Record<string, { status: string; reason: string }>;
  timeline: { event: string; description: string; created_at: string }[];
  items: {
    id: number;
    product_name: string;
    product_color: string;
    product_size: string;
    quantity: number;
    price: string;
    line_total: string;
    image_url: string | null;
    fulfillment_status?: string;
  }[];
};
type Paginated<T> = { results?: T[] };
let unauthorizedHandler: ((token: string) => void) | null = null;
export const setUnauthorizedHandler = (handler: ((token: string) => void) | null) => { unauthorizedHandler = handler; };

export async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const upload = options.body instanceof FormData;
  const writing = !!options.method && options.method.toUpperCase() !== "GET";
  const response = await fetchWithRetry(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(upload ? {} : { "Content-Type": "application/json" }),
      Accept: "application/json",
      ...(token ? { Authorization: `Token ${token}` } : {}),
      ...(options.headers || {}),
    },
  }, fetch, upload ? 120000 : writing ? 60000 : 30000).catch(error => {
    reportError(error, "api_network");
    const reason = error?.name === "TimeoutError" || error?.name === "AbortError"
      ? "The server took too long to respond." : "Could not reach ZIYAMART. Check your connection.";
    const recovery = !writing ? "Please retry."
      : path.startsWith("/checkout/") || /\/payment\/$/.test(path) ? "Check Orders before submitting again."
      : path.startsWith("/partners/") ? "The change may have been saved. Reopen the catalog or settings to check before submitting again."
      : "The change may have been saved. Refresh to check before submitting again.";
    throw new Error(`${reason} ${recovery}`);
  });
  const data =
    response.status === 204
      ? undefined
      : await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && token) unauthorizedHandler?.(token);
    const error = new Error((data as any)?.message || (data as any)?.detail ||
      (Array.isArray(data) ? data.join(" ") : Object.entries(data || {}).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(" ") : value}`).join("\n")) || "Something went wrong.");
    (error as any).details = data;
    (error as any).retryAfter = Number(response.headers?.get("Retry-After")) || 0;
    throw error;
  }
  return data as T;
}

export async function getProducts(
  params: {
    q?: string;
    category?: string;
    subcategory?: string;
    gender?: string;
    kids_age_group?: string;
    seller?: string;
    color?: string;
    size?: string;
    min_price?: string;
    max_price?: string;
    rating?: string;
    sort?: string;
    page?: string;
  } = {},
  signal?: AbortSignal,
  token?: string | null,
) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => Boolean(v)) as [string, string][],
  ).toString();
  const payload = await request<Product[] | Paginated<Product>>(
    `/products/${query ? `?${query}` : ""}`,
    { signal },
    token,
  );
  return catalogPage(payload);
}
export const getProduct = (slug: string, token?: string | null) =>
  request<Product>(`/products/${slug}/`, {}, token);
export const getCategories = () => request<Category[]>("/categories/");
export const login = (identity: string, password: string) =>
  request<AuthResponse>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ identity, password, device_name: Device.modelName || "Mobile device" }),
  });
export const signup = (data: {
  username: string;
  email: string;
  phone: string;
  password: string;
}) =>
  request<SignupResponse>("/auth/signup/", {
    method: "POST",
    body: JSON.stringify(data),
  });
export const verifyOtp = (email: string, otp: string) =>
  request<AuthResponse>("/auth/verify-otp/", {
    method: "POST",
    body: JSON.stringify({ email, otp }),
  });
export const resendSignupOtp = (email: string) =>
  request<{ message: string; email: string; retry_after: number }>("/auth/resend-otp/", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
export const requestPasswordReset = (email: string) =>
  request<{ message: string }>("/auth/password/reset/request/", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
export const confirmPasswordReset = (email: string, otp: string, password: string) =>
  request<{ message: string }>("/auth/password/reset/confirm/", {
    method: "POST",
    body: JSON.stringify({ email, otp, password }),
  });
export const changePassword = (token: string, current_password: string, new_password: string) =>
  request<{ message: string }>("/auth/password/change/", {
    method: "POST",
    body: JSON.stringify({ current_password, new_password }),
  }, token);
export const logout = (token: string) =>
  request<void>("/auth/logout/", { method: "POST" }, token);
export const getNotificationPreferences = (token: string) =>
  request<{ order_updates: boolean; payment_updates: boolean; promotions: boolean }>("/account/notifications/", {}, token);
export const updateNotificationPreferences = (token: string, data: { order_updates: boolean; payment_updates: boolean; promotions: boolean }) =>
  request<{ order_updates: boolean; payment_updates: boolean; promotions: boolean }>("/account/notifications/", { method: "PATCH", body: JSON.stringify(data) }, token);
export const registerPushDevice = (token: string, expo_push_token: string, platform: string) =>
  request<{ id: number; active: boolean }>("/account/push-devices/", { method: "POST", body: JSON.stringify({ expo_push_token, platform }) }, token);
export const deactivatePushDevice = (token: string, expo_push_token: string) =>
  request<void>("/account/push-devices/", { method: "DELETE", body: JSON.stringify({ expo_push_token }) }, token);
export const requestAccountDeletion = (token: string, reason: string) =>
  request<{ id: number; status: string }>("/account/delete-request/", { method: "POST", body: JSON.stringify({ reason }) }, token);
export const getSupportTickets = (token: string) => request<any[]>("/support/", {}, token);
export const createSupportTicket = (token: string, data: FormData) =>
  request<any>("/support/", { method: "POST", body: data }, token);
export const replySupportTicket = (token: string, id: number, data: FormData) =>
  request<any>(`/support/${id}/replies/`, { method: "POST", body: data }, token);
export const getProfile = (token: string) =>
  request<User>("/account/profile/", {}, token);
export const getCart = (token: string) => request<Cart>("/cart/", {}, token);
export const addCartItem = (token: string, variant_id: number, quantity = 1) =>
  request<CartItem>(
    "/cart/items/",
    { method: "POST", body: JSON.stringify({ variant_id, quantity }) },
    token,
  );
export const updateCartItem = (
  token: string,
  itemId: number,
  quantity: number,
) =>
  request<CartItem>(
    `/cart/items/${itemId}/`,
    { method: "PATCH", body: JSON.stringify({ quantity }) },
    token,
  );
export const deleteCartItem = (token: string, itemId: number) =>
  request<void>(`/cart/items/${itemId}/`, { method: "DELETE" }, token);
export const getAddresses = (token: string) =>
  request<Address[]>("/addresses/", {}, token);
export const addAddress = (
  token: string,
  data: Omit<Address, "id" | "is_default">,
) =>
  request<Address>(
    "/addresses/",
    { method: "POST", body: JSON.stringify(data) },
    token,
  );
export const updateAddress = (
  token: string,
  id: number,
  data: Omit<Address, "id" | "is_default">,
) =>
  request<Address>(
    `/addresses/${id}/`,
    { method: "PATCH", body: JSON.stringify(data) },
    token,
  );
export const deleteAddress = (token: string, id: number) =>
  request<void>(`/addresses/${id}/`, { method: "DELETE" }, token);
export const setDefaultAddress = (token: string, id: number) =>
  request<Address>(`/addresses/${id}/default/`, { method: "POST" }, token);
export const getWishlist = (token: string) =>
  request<Product[]>("/wishlist/", {}, token);
export const addWishlist = (token: string, productId: number) =>
  request<{ is_wishlisted: boolean }>(
    `/wishlist/${productId}/`,
    { method: "POST" },
    token,
  );
export const removeWishlist = (token: string, productId: number) =>
  request<void>(`/wishlist/${productId}/`, { method: "DELETE" }, token);
export const getRestaurants = (pincode = "") =>
  request<Restaurant[]>(
    `/food/restaurants/${pincode ? `?pincode=${encodeURIComponent(pincode)}` : ""}`,
  );
export const getRestaurant = (slug: string) =>
  request<Restaurant>(`/food/restaurants/${slug}/`);
export const getFoodCart = (token: string) =>
  request<ServiceCart<FoodCartItem>>("/food/cart/", {}, token);
export const addFoodCartItem = (
  token: string,
  option_id: number,
  replace_cart = false,
  quantity = 1,
  note = "",
) =>
  request<ServiceCart<FoodCartItem>>(
    "/food/cart/items/",
    {
      method: "POST",
      body: JSON.stringify({ option_id, replace_cart, quantity, note }),
    },
    token,
  );
export const updateFoodCartItem = (
  token: string,
  id: number,
  quantity: number,
) =>
  request<ServiceCart<FoodCartItem>>(
    `/food/cart/items/${id}/`,
    { method: "PATCH", body: JSON.stringify({ quantity }) },
    token,
  );
export const deleteFoodCartItem = (token: string, id: number) =>
  request<ServiceCart<FoodCartItem>>(
    `/food/cart/items/${id}/`,
    { method: "DELETE" },
    token,
  );
export const getGroceryStores = (pincode = "") =>
  request<GroceryStore[]>(
    `/groceries/stores/${pincode ? `?pincode=${encodeURIComponent(pincode)}` : ""}`,
  );
export const getGroceryStore = (slug: string) =>
  request<GroceryStore & { products: GroceryProduct[] }>(
    `/groceries/stores/${slug}/?include_products=false`,
  );
export const getGroceryProducts = async (
  params: { q?: string; store?: string; category?: string; page?: string } = {},
  signal?: AbortSignal,
) => {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => Boolean(v)) as [string, string][],
  ).toString();

  const payload = await request<GroceryProduct[] | Paginated<GroceryProduct>>(
    `/groceries/products/${query ? `?${query}` : ""}`,
    { signal },
  );

  return catalogPage(payload);
};
export const getGroceryCategories = () => request<{ id: number; name: string; slug: string }[]>("/groceries/categories/");
export const getGroceryCart = (token: string) =>
  request<ServiceCart<GroceryCartItem>>("/groceries/cart/", {}, token);
export const addGroceryCartItem = (
  token: string,
  product_id: number,
  replace_cart = false,
) =>
  request<ServiceCart<GroceryCartItem>>(
    "/groceries/cart/items/",
    { method: "POST", body: JSON.stringify({ product_id, replace_cart }) },
    token,
  );
export const updateGroceryCartItem = (
  token: string,
  id: number,
  quantity: number,
) =>
  request<ServiceCart<GroceryCartItem>>(
    `/groceries/cart/items/${id}/`,
    { method: "PATCH", body: JSON.stringify({ quantity }) },
    token,
  );
export const deleteGroceryCartItem = (token: string, id: number) =>
  request<ServiceCart<GroceryCartItem>>(
    `/groceries/cart/items/${id}/`,
    { method: "DELETE" },
    token,
  );
export const getCheckoutQuote = (
  token: string,
  kind: "shop" | "food" | "grocery",
  address_id: number,
  location?: { latitude: string; longitude: string; gps_accuracy_meters: number; gps_captured_at: string },
) =>
  request<CheckoutQuote>(
    `/checkout/${kind}/quote/`,
    { method: "POST", body: JSON.stringify({ address_id, location }) },
    token,
  );
export const checkoutShop = (
  token: string,
  address_id: number,
  quote_id: string,
  idempotency_key: string,
  payment_method: "cod" | "online" = "cod",
) =>
  request<any>(
    "/checkout/shop/",
    {
      method: "POST",
      body: JSON.stringify({ address_id, quote_id, idempotency_key, payment_method }),
    },
    token,
  );
export const checkoutFood = (
  token: string,
  address_id: number,
  items: { option_id: number; quantity: number; note?: string }[],
  include_cutlery: boolean,
  delivery_note: string,
  quote_id: string,
  idempotency_key: string,
  payment_method: "cod" | "online" = "cod",
) =>
  request<any>(
    "/checkout/food/",
    {
      method: "POST",
      body: JSON.stringify({
        address_id,
        items,
        include_cutlery,
        delivery_note,
        quote_id,
        idempotency_key,
        payment_method,
      }),
    },
    token,
  );
export const checkoutGrocery = (
  token: string,
  address_id: number,
  items: { product_id: number; quantity: number }[],
  substitution_preference: string,
  quote_id: string,
  idempotency_key: string,
  payment_method: "cod" | "online" = "cod",
) =>
  request<any>(
    "/checkout/grocery/",
    {
      method: "POST",
      body: JSON.stringify({
        address_id,
        items,
        substitution_preference,
        quote_id,
        idempotency_key,
        payment_method,
      }),
    },
    token,
  );
export const clearShopCart = (token: string) =>
  request<void>("/cart/", { method: "DELETE" }, token);
export const clearFoodCart = (token: string) =>
  request<void>("/food/cart/", { method: "DELETE" }, token);
export const clearGroceryCart = (token: string) =>
  request<void>("/groceries/cart/", { method: "DELETE" }, token);
export const getOrders = (token: string) =>
  request<Order[]>("/orders/", {}, token);
export const cancelOrder = (token: string, order: Order, reason: string) =>
  request<Order>(
    `/orders/${order.kind}/${order.id}/cancel/`,
    { method: "POST", body: JSON.stringify({ reason }) },
    token,
  );
export const createCareRequest = (
  token: string,
  order: Order,
  request_type: "support" | "return",
  reason: string,
  message: string,
) =>
  request<any>(
    `/orders/${order.kind}/${order.id}/care/`,
    { method: "POST", body: JSON.stringify({ request_type, reason, message }) },
    token,
  );
export const updateProfile = (
  token: string,
  data: { first_name: string; last_name: string; phone: string },
) =>
  request<User>(
    "/account/profile/",
    { method: "PATCH", body: JSON.stringify(data) },
    token,
  );
