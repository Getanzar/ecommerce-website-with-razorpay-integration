import { StatusBar } from "expo-status-bar";
import { LinearGradient } from "expo-linear-gradient";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  Modal,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as SecureStore from "expo-secure-store";
import Constants from "expo-constants";
import PartnerWorkspace from "./src/PartnerWorkspace";
import CustomerOrderTools from "./src/CustomerOrderTools";
import AccountTools from "./src/AccountTools";
import usePushRegistration from "./src/usePushRegistration";
import { payOrder, recoverPayment } from "./src/nativePayments";
import NotificationInbox, { NotificationTarget } from "./src/NotificationInbox";
import { stopTracking } from "./src/backgroundTracking";
import { AppErrorBoundary } from "./src/telemetry";
import { useCatalog } from "./src/useCatalog";
import {
  Address,
  Cart,
  Category,
  CheckoutQuote,
  FoodCartItem,
  GroceryCartItem,
  GroceryProduct,
  GroceryStore,
  MenuItem,
  Order,
  Product,
  Restaurant,
  ServiceCart,
  User,
  addAddress,
  addCartItem,
  addFoodCartItem,
  addGroceryCartItem,
  addWishlist,
  cancelOrder,
  checkoutFood,
  checkoutGrocery,
  checkoutShop,
  clearFoodCart,
  clearGroceryCart,
  clearShopCart,
  createCareRequest,
  deleteAddress,
  deleteCartItem,
  deleteFoodCartItem,
  deleteGroceryCartItem,
  getAddresses,
  getCart,
  getCategories,
  getCheckoutQuote,
  getFoodCart,
  getGroceryCart,
  getGroceryProducts,
  getGroceryCategories,
  getGroceryStore,
  getGroceryStores,
  getOrders,
  getProduct,
  getProducts,
  getProfile,
  getRestaurant,
  getRestaurants,
  getWishlist,
  login,
  logout,
  requestPasswordReset,
  resendSignupOtp,
  confirmPasswordReset,
  removeWishlist,
  setDefaultAddress,
  setUnauthorizedHandler,
  signup,
  updateAddress,
  updateCartItem,
  updateFoodCartItem,
  updateGroceryCartItem,
  updateProfile,
  verifyOtp,
} from "./src/api";

type Tab = "Home" | "Search" | "Cart" | "Account" | "Categories";
type Service = "shop" | "food" | "grocery";
type FoodCartRow = {
  id: number;
  item: MenuItem;
  option_id: number;
  option_name: string;
  restaurant_name: string;
  quantity: number;
  note: string;
};
type GroceryCartRow = { id: number; product: GroceryProduct; quantity: number };
const C = {
  ink: "#17243A",
  muted: "#718096",
  cream: "#FFF8EC",
  orange: "#F36D2F",
  dark: "#D84B16",
  green: "#0F8B6D",
  line: "#ECE7DE",
  white: "#FFFFFF",
};
const BRAND_MARK = require("./assets/brand-mark.png");
const money = (value: string) =>
  `₹${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const foodRows = (cart: ServiceCart<FoodCartItem>): FoodCartRow[] =>
  cart.items.map((row) => ({
    id: row.id,
    option_id: row.option_id,
    option_name: row.option_name,
    restaurant_name: row.restaurant_name,
    quantity: row.quantity,
    note: row.note,
    item: {
      id: row.option_id,
      name: row.name,
      description: "",
      food_type: "",
      image_url: row.image_url,
      section: "",
      starting_price: row.unit_price,
      options: [
        { id: row.option_id, name: row.option_name, price: row.unit_price },
      ],
    },
  }));
const groceryRows = (cart: ServiceCart<GroceryCartItem>): GroceryCartRow[] =>
  cart.items.map((row) => ({
    id: row.id,
    quantity: row.quantity,
    product: {
      id: row.product_id,
      name: row.name,
      brand: "",
      image_url: row.image_url,
      unit: row.unit,
      mrp: row.unit_price,
      price: row.unit_price,
      stock: row.stock,
      is_perishable: false,
      store_name: row.store_name,
      category: { id: 0, name: "", slug: "", image_url: null },
    },
  }));

function ProductCard({
  product,
  onOpen,
  onWishlist,
}: {
  product: Product;
  onOpen: () => void;
  onWishlist?: () => void;
}) {
  return (
    <Pressable style={s.card} onPress={onOpen}>
      <View style={s.imageWrap}>
        {product.image_url ? (
          <Image source={{ uri: product.image_url }} style={s.productImage} />
        ) : (
          <Text style={s.placeholder}>ZM</Text>
        )}
        <Pressable
          accessibilityLabel={
            product.is_wishlisted ? "Remove from wishlist" : "Add to wishlist"
          }
          style={s.heart}
          onPress={(event) => {
            event.stopPropagation();
            onWishlist?.();
          }}
        >
          <Text style={product.is_wishlisted && s.heartActive}>
            {product.is_wishlisted ? "♥" : "♡"}
          </Text>
        </Pressable>
      </View>
      <Text style={s.productName} numberOfLines={2}>
        {product.name}
      </Text>
      <Text style={s.price}>{money(product.price)}</Text>
      <Text style={s.viewDetails}>View details →</Text>
    </Pressable>
  );
}

function Field({
  label,
  value,
  onChange,
  secure = false,
  keyboard = "default",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  secure?: boolean;
  keyboard?: any;
}) {
  return (
    <View style={s.field}>
      <Text style={s.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        secureTextEntry={secure}
        keyboardType={keyboard}
        autoCapitalize="none"
        style={s.fieldInput}
      />
    </View>
  );
}

function AuthModal({
  visible,
  onClose,
  onAuthenticated,
}: {
  visible: boolean;
  onClose: () => void;
  onAuthenticated: (token: string, user: User) => void;
}) {
  const [mode, setMode] = useState<"login" | "signup" | "resume" | "otp" | "forgot" | "reset">("login");
  const [identity, setIdentity] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [resendAt, setResendAt] = useState(0);
  const [resendSeconds, setResendSeconds] = useState(0);
  useEffect(() => {
    const tick = () => setResendSeconds(Math.max(0, Math.ceil((resendAt - Date.now()) / 1000)));
    tick();
    if (!resendAt) return;
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [resendAt]);
  const showAuthError = (error: any) => {
    const details = error.details?.errors || error.details;
    const first = details && typeof details === "object" ? Object.values(details).flat()[0] : null;
    setMessage(String(first || error.message));
    if (error.retryAfter > 0) setResendAt(Date.now() + error.retryAfter * 1000);
  };
  const resend = async () => {
    if (busy || resendSeconds > 0) return;
    setBusy(true);
    setMessage("");
    try {
      const result = mode === "reset" ? await requestPasswordReset(email) : await resendSignupOtp(email);
      setOtp("");
      setResendAt(Date.now() + 60000);
      setMessage(result.message);
    } catch (error: any) { showAuthError(error); }
    finally { setBusy(false); }
  };
  const submit = async () => {
    if (busy) return;
    setBusy(true);
    setMessage("");
    try {
      if (mode === "login") {
        const result = await login(identity, password);
        onAuthenticated(result.token, result.user);
        onClose();
      } else if (mode === "signup") {
        const result = await signup({ username, email, phone, password });
        setEmail(result.email);
        setOtp("");
        setResendAt(Date.now() + 60000);
        setMode("otp");
        setMessage(
          result.debug_otp
            ? `Local test code: ${result.debug_otp}`
            : result.message,
        );
      } else if (mode === "resume") {
        const result = await resendSignupOtp(email);
        setEmail(result.email);
        setOtp("");
        setResendAt(Date.now() + result.retry_after * 1000);
        setMode("otp");
        setMessage(result.message);
      } else if (mode === "otp") {
        const result = await verifyOtp(email, otp);
        onAuthenticated(result.token, result.user);
        onClose();
      } else if (mode === "forgot") {
        const result = await requestPasswordReset(email);
        setOtp("");
        setResendAt(Date.now() + 60000);
        setMode("reset");
        setMessage(result.message);
      } else {
        const result = await confirmPasswordReset(email, otp, password);
        setMode("login");
        setIdentity(email);
        setOtp("");
        setPassword("");
        setMessage(result.message);
      }
    } catch (error: any) {
      showAuthError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={s.authPage} edges={["top", "bottom"]}>
        <ScrollView
          contentContainerStyle={s.authInner}
          keyboardShouldPersistTaps="handled"
        >
          <View style={s.authTop}>
            <View style={s.logo}>
              <Image source={BRAND_MARK} style={s.logoImage} />
            </View>
            <Pressable onPress={onClose}>
              <Text style={s.close}>×</Text>
            </Pressable>
          </View>
          <Text style={s.authTitle}>
            {mode === "login"
              ? "Welcome back"
              : mode === "signup"
                ? "Create your account"
                : mode === "otp" || mode === "resume"
                  ? "Verify your email"
                  : mode === "forgot"
                    ? "Reset your password"
                    : "Choose a new password"}
          </Text>
          <Text style={s.authCopy}>
            {mode === "otp" || mode === "reset"
              ? `Enter the six-digit code sent to ${email}.`
              : "Your orders, wishlist and addresses stay safely synced."}
          </Text>
          {mode === "login" && (
            <>
              <Field
                label="Email or username"
                value={identity}
                onChange={setIdentity}
              />
              <Pressable onPress={() => { setMode("forgot"); setEmail(identity.includes("@") ? identity : ""); setMessage(""); }}>
                <Text style={s.link}>Forgot password?</Text>
              </Pressable>
              <Field
                label="Password"
                value={password}
                onChange={setPassword}
                secure
              />
            </>
          )}
          {mode === "signup" && (
            <>
              <Field label="Username" value={username} onChange={setUsername} />
              <Field
                label="Email"
                value={email}
                onChange={setEmail}
                keyboard="email-address"
              />
              <Field
                label="Mobile number"
                value={phone}
                onChange={setPhone}
                keyboard="phone-pad"
              />
              <Field
                label="Password"
                value={password}
                onChange={setPassword}
                secure
              />
            </>
          )}
          {mode === "otp" && (
            <Field
              label="Verification code"
              value={otp}
              onChange={setOtp}
              keyboard="number-pad"
            />
          )}
          {(mode === "forgot" || mode === "resume") && <Field label="Account email" value={email} onChange={setEmail} keyboard="email-address" />}
          {mode === "reset" && (
            <>
              <Field label="Reset code" value={otp} onChange={setOtp} keyboard="number-pad" />
              <Field label="New password" value={password} onChange={setPassword} secure />
            </>
          )}
          {!!message && <Text style={s.formMessage}>{message}</Text>}
          <Pressable
            disabled={busy}
            style={[s.primary, busy && s.disabled]}
            onPress={submit}
          >
            {busy ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={s.primaryText}>
                {mode === "login"
                  ? "Sign in"
                  : mode === "signup"
                    ? "Create account"
                    : mode === "otp"
                      ? "Verify and continue"
                      : mode === "resume"
                        ? "Send verification code"
                        : mode === "forgot"
                        ? "Send reset code"
                        : "Change password"}
              </Text>
            )}
          </Pressable>
          {(mode === "otp" || mode === "reset") && (
            <Pressable accessibilityRole="button" disabled={busy || resendSeconds > 0} onPress={resend}>
              <Text style={s.authSwitch}>{resendSeconds > 0 ? `Resend code in ${resendSeconds}s` : "Resend code"}</Text>
            </Pressable>
          )}
          {(mode === "login" || mode === "signup") && (
            <Pressable disabled={busy} accessibilityRole="button" onPress={() => { setMode("resume"); setMessage(""); setOtp(""); }}>
              <Text style={s.authSwitch}>Finish email verification</Text>
            </Pressable>
          )}
          {(mode === "login" || mode === "signup") && (
            <Pressable
              disabled={busy}
              onPress={() => {
                setMode(mode === "login" ? "signup" : "login");
                setMessage("");
              }}
            >
              <Text style={s.authSwitch}>
                {mode === "login"
                  ? "New to ZIYAMART? Create an account"
                  : "Already registered? Sign in"}
              </Text>
            </Pressable>
          )}
          {(mode === "forgot" || mode === "reset" || mode === "resume" || mode === "otp") && (
            <Pressable disabled={busy} onPress={() => { setMode("login"); setMessage(""); }}><Text style={s.authSwitch}>Back to sign in</Text></Pressable>
          )}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function Header({
  count,
  location,
  onLocation,
  onCart,
  onLogo,
}: {
  count: number;
  location: string;
  onLocation: () => void;
  onCart: () => void;
  onLogo: () => void;
}) {
  return (
    <View style={s.header}>
      <Pressable onPress={onLocation} style={s.locationButton}>
        <Text style={s.eyebrow}>DELIVERING TO</Text>
        <Text style={s.location} numberOfLines={1}>
          {location}⌄
        </Text>
      </Pressable>
      <Pressable
        accessibilityLabel="Go to ZIYAMART home"
        onPress={onLogo}
        style={s.logo}
      >
        <Image source={BRAND_MARK} style={s.logoImage} />
      </Pressable>
      <Pressable
        accessibilityLabel="Open all carts"
        onPress={onCart}
        style={s.headerCart}
      >
        <Text style={s.cartIcon}>🛍</Text>
        {count > 0 && <Text style={s.badge}>{count}</Text>}
      </Pressable>
    </View>
  );
}

function ServiceStrip({
  selected,
  onSelect,
}: {
  selected: Service;
  onSelect: (service: Service) => void;
}) {
  const items: [Service, string, string][] = [
    ["shop", "🛍️", "Shop"],
    ["food", "🍲", "Food"],
    ["grocery", "🥬", "Groceries"],
  ];
  return (
    <View style={s.serviceStrip}>
      {items.map(([value, icon, label]) => (
        <Pressable
          key={value}
          style={[s.serviceButton, selected === value && s.serviceActive]}
          onPress={() => onSelect(value)}
        >
          <Text style={s.serviceIcon}>{icon}</Text>
          <Text
            style={[s.serviceLabel, selected === value && s.serviceLabelActive]}
          >
            {label}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

function LocalServiceScreen({
  service,
  pincode,
  token,
  onLogin,
  foodCart,
  setFoodCart,
  groceryCart,
  setGroceryCart,
  onOpenCart,
}: {
  service: Exclude<Service, "shop">;
  pincode: string;
  token: string | null;
  onLogin: () => void;
  foodCart: FoodCartRow[];
  setFoodCart: React.Dispatch<React.SetStateAction<FoodCartRow[]>>;
  groceryCart: GroceryCartRow[];
  setGroceryCart: React.Dispatch<React.SetStateAction<GroceryCartRow[]>>;
  onOpenCart: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [stores, setStores] = useState<GroceryStore[]>([]);
  const [groceryGroups, setGroceryGroups] = useState<{ id: number; name: string; slug: string }[]>([]);
  const [restaurant, setRestaurant] = useState<Restaurant | null>(null);
  const [store, setStore] = useState<
    (GroceryStore & { products: GroceryProduct[] }) | null
  >(null);
  const [localQuery, setLocalQuery] = useState("");
  const [groceryCategory, setGroceryCategory] = useState("");
  const groceryPages = useCatalog<GroceryProduct>(
    JSON.stringify([service, pincode, store?.slug, localQuery, groceryCategory]),
    (page, signal) => getGroceryProducts({ store: store?.slug, q: localQuery, category: groceryCategory, page: String(page) }, signal),
    service === "grocery" && !!store,
  );
  const [foodDetail, setFoodDetail] = useState<MenuItem | null>(null);
  const [groceryDetail, setGroceryDetail] = useState<GroceryProduct | null>(
    null,
  );
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setRestaurant(null);
    setStore(null);
    const action =
      service === "food"
        ? getRestaurants(pincode)
        : Promise.all([getGroceryStores(pincode), getGroceryCategories()]);
    Promise.resolve(action)
      .then((data: any) => {
        if (!active) return;
        if (service === "food") setRestaurants(data);
        else {
          setStores(data[0]);
          setGroceryGroups(data[1]);
        }
      })
      .catch(() => { if (active) setError("This service could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [service, pincode]);
  const title = service === "food" ? "Food delivery" : "Groceries";
  const subtitle =
    service === "food"
      ? "Fresh meals from nearby restaurants"
      : "Daily essentials from local stores";
  if (loading)
    return (
      <View style={s.servicePage}>
        <ActivityIndicator color={C.green} size="large" />
      </View>
    );
  const addFood = async (
    item: MenuItem,
    replace = false,
    quantity = 1,
    note = "",
  ) => {
    const option = item.options[0];
    if (!option)
      return Alert.alert("Unavailable", "No purchasable option is available.");
    if (!token) return onLogin();
    try {
      setFoodCart(
        foodRows(
          await addFoodCartItem(token, option.id, replace, quantity, note),
        ),
      );
    } catch (error: any) {
      if (error.details?.replace_required)
        Alert.alert("Replace food cart?", error.message, [
          { text: "Cancel", style: "cancel" },
          {
            text: "Replace",
            style: "destructive",
            onPress: () => addFood(item, true, quantity, note),
          },
        ]);
      else Alert.alert("Could not add item", error.message);
    }
  };
  const addGrocery = async (product: GroceryProduct, replace = false) => {
    if (!token) return onLogin();
    try {
      setGroceryCart(
        groceryRows(await addGroceryCartItem(token, product.id, replace)),
      );
    } catch (error: any) {
      if (error.details?.replace_required)
        Alert.alert("Replace grocery cart?", error.message, [
          { text: "Cancel", style: "cancel" },
          {
            text: "Replace",
            style: "destructive",
            onPress: () => addGrocery(product, true),
          },
        ]);
      else Alert.alert("Could not add item", error.message);
    }
  };
  const serviceItems =
    service === "food"
      ? foodCart.map((row) => ({
          name: row.item.name,
          meta: row.option_name,
          image_url: row.item.image_url,
          price:
            row.item.options.find((o) => o.id === row.option_id)?.price ||
            row.item.starting_price,
          quantity: row.quantity,
        }))
      : groceryCart.map((row) => ({
          name: row.product.name,
          meta: row.product.unit,
          image_url: row.product.image_url,
          price: row.product.price,
          quantity: row.quantity,
        }));
  const groceryItems = groceryPages.items;
  if (restaurant)
    return (
      <>
        <ScrollView contentContainerStyle={s.serviceContent}>
          <Pressable onPress={() => setRestaurant(null)} style={s.back}>
            <Text style={s.backText}>‹ Restaurants</Text>
          </Pressable>
          {restaurant.image_url && (
            <Image
              source={{ uri: restaurant.image_url }}
              style={s.restaurantHero}
            />
          )}
          <Text style={s.serviceTitle}>{restaurant.name}</Text>
          <Text style={s.serviceSubtitle}>
            {restaurant.cuisine} · {restaurant.preparation_minutes} min
          </Text>
          {restaurant.menu_items?.map((item) => (
            <Pressable
              key={item.id}
              style={s.menuCard}
              onPress={() => setFoodDetail(item)}
            >
              <View style={s.menuCopy}>
                <Text style={s.storeName}>{item.name}</Text>
                <Text style={s.storeMeta}>
                  {item.food_type === "veg" ? "🟢 Veg" : "🔴 Non-veg"} ·{" "}
                  {item.section}
                </Text>
                <Text style={s.description} numberOfLines={2}>
                  {item.description}
                </Text>
                <Text style={s.price}>From {money(item.starting_price)}</Text>
                <Text style={s.viewDetails}>View details →</Text>
              </View>
              {item.image_url ? (
                <Image source={{ uri: item.image_url }} style={s.menuImage} />
              ) : (
                <View style={s.menuImage} />
              )}
            </Pressable>
          ))}
          {!!foodCart.length && (
            <Pressable style={s.stickyCheckout} onPress={onOpenCart}>
              <Text style={s.primaryText}>
                {foodCart.reduce((n, r) => n + r.quantity, 0)} items · View food
                cart
              </Text>
            </Pressable>
          )}
        </ScrollView>
        <FoodDetailModal
          item={foodDetail}
          restaurant={restaurant}
          onClose={() => setFoodDetail(null)}
          onAdd={addFood}
        />
      </>
    );
  return (
    <ScrollView contentContainerStyle={s.serviceContent}>
      {store && (
        <Pressable
          style={s.back}
          onPress={() => {
            setStore(null);
            setGroceryCategory("");
            setLocalQuery("");
          }}
        >
          <Text style={s.backText}>‹ All grocery stores</Text>
        </Pressable>
      )}
      <Text style={s.serviceTitle}>{store?.name || title}</Text>
      <Text style={s.serviceSubtitle}>
        {store
          ? `${store.estimated_delivery_minutes} min · Delivery ${money(store.delivery_fee)}`
          : subtitle}
      </Text>
      {!!error && <Text style={s.errorText}>{error}</Text>}
      {service === "food" &&
        restaurants.map((row) => (
          <Pressable
            key={row.id}
            style={s.storeCard}
            onPress={async () => {
              try {
                setRestaurant(await getRestaurant(row.slug));
              } catch {
                Alert.alert("Could not open menu", "Please try again.");
              }
            }}
          >
            {row.image_url ? (
              <Image source={{ uri: row.image_url }} style={s.storeImage} />
            ) : (
              <View style={s.storeFallback}>
                <Text style={s.storeEmoji}>🍲</Text>
              </View>
            )}
            <View style={s.storeCopy}>
              <Text style={s.storeName}>{row.name}</Text>
              <Text style={s.storeMeta}>
                {row.cuisine || "Local favourites"} · {row.preparation_minutes}{" "}
                min
              </Text>
              <Text style={s.storeMeta}>
                Delivery {money(row.delivery_fee)}
              </Text>
              <Text style={s.openText}>View menu →</Text>
            </View>
          </Pressable>
        ))}
      {service === "grocery" &&
        !store &&
        stores.map((row) => (
          <Pressable
            key={row.id}
            style={s.storeCard}
            onPress={async () => {
              try {
                setStore(await getGroceryStore(row.slug));
              } catch {
                Alert.alert("Could not open store", "Please try again.");
              }
            }}
          >
            {row.image_url ? (
              <Image source={{ uri: row.image_url }} style={s.storeImage} />
            ) : (
              <View style={s.storeFallback}>
                <Text style={s.storeEmoji}>🥬</Text>
              </View>
            )}
            <View style={s.storeCopy}>
              <Text style={s.storeName}>{row.name}</Text>
              <Text style={s.storeMeta}>
                {row.estimated_delivery_minutes} min · Delivery{" "}
                {money(row.delivery_fee)}
              </Text>
              <Text style={s.storeMeta}>
                Minimum order {money(row.minimum_order)}
              </Text>
              <Text style={s.openText}>Shop this store →</Text>
            </View>
          </Pressable>
        ))}
      {service === "grocery" && store && (
        <>
          <TextInput
            value={localQuery}
            onChangeText={setLocalQuery}
            placeholder="Search this store"
            style={s.searchInput}
          />
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={s.filterChips}
          >
            <Pressable
              style={[s.filterChip, !groceryCategory && s.filterChipActive]}
              onPress={() => setGroceryCategory("")}
            >
              <Text>All</Text>
            </Pressable>
            {groceryGroups.map((group) => (
              <Pressable
                key={group.slug}
                style={[
                  s.filterChip,
                  groceryCategory === group.slug && s.filterChipActive,
                ]}
                onPress={() => setGroceryCategory(group.slug)}
              >
                <Text>{group.name}</Text>
              </Pressable>
            ))}
          </ScrollView>
        </>
      )}
      {service !== "food" && store && (
        <>
        {groceryPages.loading && <ActivityIndicator />}
        <View style={s.groceryGrid}>
          {groceryItems.map((row) => (
            <Pressable
              key={row.id}
              style={s.groceryCard}
              onPress={() => setGroceryDetail(row)}
            >
              {row.image_url ? (
                <Image source={{ uri: row.image_url }} style={s.groceryImage} />
              ) : (
                <View style={s.groceryFallback}>
                  <Text style={s.storeEmoji}>🥫</Text>
                </View>
              )}
              <Text style={s.groceryName} numberOfLines={2}>
                {row.name}
              </Text>
              <Text style={s.storeMeta}>
                {row.brand || row.store_name} · {row.unit}
              </Text>
              <Text style={s.price}>{money(row.price)}</Text>
              <Text style={s.stockText}>{row.stock} available</Text>
              <Text style={s.viewDetails}>View details →</Text>
            </Pressable>
          ))}
        </View>
        <CatalogMore catalog={groceryPages} />
        {!groceryPages.loading && !groceryPages.error && !groceryItems.length && <Text style={s.emptyCopy}>No products match these filters.</Text>}
        </>
      )}
      {!error &&
        ((service === "food" && !restaurants.length) ||
          (service === "grocery" && !stores.length)) && (
          <View style={s.emptyService}>
            <Text style={s.emptyIcon}>{service === "food" ? "🍲" : "🥬"}</Text>
            <Text style={s.pageTitle}>Coming to your area</Text>
            <Text style={s.emptyCopy}>
              No approved {title.toLowerCase()} inventory is currently published
              on ZIYAMART. It will appear here automatically when a seller adds
              it.
            </Text>
          </View>
        )}
      {!!groceryCart.length && (
        <Pressable style={s.stickyCheckout} onPress={onOpenCart}>
          <Text style={s.primaryText}>
            {groceryCart.reduce((n, r) => n + r.quantity, 0)} items · View
            grocery cart
          </Text>
        </Pressable>
      )}
      <GroceryDetailModal
        product={groceryDetail}
        onClose={() => setGroceryDetail(null)}
        onAdd={addGrocery}
      />
    </ScrollView>
  );
}

function FoodDetailModal({
  item,
  restaurant,
  onClose,
  onAdd,
}: {
  item: MenuItem | null;
  restaurant: Restaurant;
  onClose: () => void;
  onAdd: (
    item: MenuItem,
    replace?: boolean,
    quantity?: number,
    note?: string,
  ) => void;
}) {
  const [optionId, setOptionId] = useState<number | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [note, setNote] = useState("");
  useEffect(() => {
    setOptionId(item?.options[0]?.id || null);
    setQuantity(1);
    setNote("");
  }, [item?.id]);
  if (!item) return null;
  const chosen = item.options.find((o) => o.id === optionId) || item.options[0];
  return (
    <Modal
      visible
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={s.authPage} edges={["top", "bottom"]}>
        <View style={s.modalHeader}>
          <Text style={s.modalTitle}>Food details</Text>
          <Pressable onPress={onClose}>
            <Text style={s.close}>×</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={s.detailPage}>
          {item.image_url ? (
            <Image source={{ uri: item.image_url }} style={s.detailImageWrap} />
          ) : (
            <View style={s.detailImageWrap}>
              <Text style={s.detailPlaceholder}>🍲</Text>
            </View>
          )}
          <Text style={s.detailTitle}>{item.name}</Text>
          <Text style={s.storeMeta}>
            {item.food_type === "veg" ? "🟢 Vegetarian" : "🔴 Non-vegetarian"} ·{" "}
            {item.section}
          </Text>
          <Text style={s.description}>
            {item.description ||
              "Freshly prepared by the restaurant after your order is confirmed."}
          </Text>
          <View style={s.infoGrid}>
            <View style={s.infoHalf}>
              <Text style={s.infoLabel}>RESTAURANT</Text>
              <Text style={s.infoValue}>{restaurant.name}</Text>
            </View>
            <View style={s.infoHalf}>
              <Text style={s.infoLabel}>PREPARATION</Text>
              <Text style={s.infoValue}>
                {restaurant.preparation_minutes} min
              </Text>
            </View>
          </View>
          <Text style={s.sectionTitle}>Choose an option</Text>
          <View style={s.variants}>
            {item.options.map((option) => (
              <Pressable
                key={option.id}
                style={[s.variant, optionId === option.id && s.optionSelected]}
                onPress={() => setOptionId(option.id)}
              >
                <Text style={s.variantText}>{option.name}</Text>
                <Text style={s.variantPrice}>{money(option.price)}</Text>
              </Pressable>
            ))}
          </View>
          <Text style={s.sectionTitle}>Quantity</Text>
          <View style={s.qty}>
            <Pressable onPress={() => setQuantity(Math.max(1, quantity - 1))}>
              <Text style={s.qtyBtn}>−</Text>
            </Pressable>
            <Text style={s.qtyValue}>{quantity}</Text>
            <Pressable onPress={() => setQuantity(Math.min(20, quantity + 1))}>
              <Text style={s.qtyBtn}>＋</Text>
            </Pressable>
          </View>
          <Text style={s.sectionTitle}>Cooking instructions</Text>
          <TextInput
            value={note}
            onChangeText={(value) => setNote(value.slice(0, 300))}
            placeholder="Example: less spicy, no onion"
            multiline
            style={[s.fieldInput, s.noteInput]}
          />
          <View style={s.stockBanner}>
            <Text style={s.stockBannerText}>
              ✓ Prepared fresh · Secure COD available
            </Text>
          </View>
          <Pressable
            disabled={!chosen}
            style={[s.primary, !chosen && s.disabled]}
            onPress={() => {
              onAdd(
                { ...item, options: chosen ? [chosen] : [] },
                false,
                quantity,
                note,
              );
              onClose();
            }}
          >
            <Text style={s.primaryText}>
              Add {chosen ? money(String(Number(chosen.price) * quantity)) : ""}{" "}
              to food cart
            </Text>
          </Pressable>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function GroceryDetailModal({
  product,
  onClose,
  onAdd,
}: {
  product: GroceryProduct | null;
  onClose: () => void;
  onAdd: (product: GroceryProduct) => void;
}) {
  if (!product) return null;
  const saving = Number(product.mrp) - Number(product.price);
  return (
    <Modal
      visible
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={s.authPage} edges={["top", "bottom"]}>
        <View style={s.modalHeader}>
          <Text style={s.modalTitle}>Product details</Text>
          <Pressable onPress={onClose}>
            <Text style={s.close}>×</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={s.detailPage}>
          {product.image_url ? (
            <Image
              source={{ uri: product.image_url }}
              style={s.detailImageWrap}
            />
          ) : (
            <View style={s.detailImageWrap}>
              <Text style={s.detailPlaceholder}>🥬</Text>
            </View>
          )}
          <Text style={s.detailTitle}>{product.name}</Text>
          <Text style={s.storeMeta}>
            {product.brand || "Local selection"} · {product.unit}
          </Text>
          <View style={s.ratingRow}>
            <Text style={s.detailPrice}>{money(product.price)}</Text>
            {Number(product.mrp) > Number(product.price) && (
              <Text style={s.mrp}>MRP {money(product.mrp)}</Text>
            )}
          </View>
          {saving > 0 && (
            <View style={s.stockBanner}>
              <Text style={s.stockBannerText}>
                You save {money(String(saving))}
              </Text>
            </View>
          )}
          <View style={s.infoGrid}>
            <View style={s.infoHalf}>
              <Text style={s.infoLabel}>SOLD BY</Text>
              <Text style={s.infoValue}>{product.store_name}</Text>
            </View>
            <View style={s.infoHalf}>
              <Text style={s.infoLabel}>AVAILABILITY</Text>
              <Text style={s.infoValue}>{product.stock} in stock</Text>
            </View>
          </View>
          <Text style={s.sectionTitle}>Product information</Text>
          <View style={s.descriptionBox}>
            <Text style={s.description}>
              Pack size: {product.unit}
              {product.is_perishable ? " · Perishable item" : ""}. Final
              availability and delivery eligibility are verified at checkout.
            </Text>
          </View>
          <View style={s.benefits}>
            <View style={s.benefit}>
              <Text style={s.benefitIcon}>✓</Text>
              <Text style={s.benefitTitle}>Stock verified</Text>
            </View>
            <View style={s.benefit}>
              <Text style={s.benefitIcon}>₹</Text>
              <Text style={s.benefitTitle}>COD available</Text>
            </View>
            <View style={s.benefit}>
              <Text style={s.benefitIcon}>⌖</Text>
              <Text style={s.benefitTitle}>Local delivery</Text>
            </View>
          </View>
          <Pressable
            disabled={product.stock < 1}
            style={[s.primary, product.stock < 1 && s.disabled]}
            onPress={() => {
              onAdd(product);
              onClose();
            }}
          >
            <Text style={s.primaryText}>
              {product.stock ? "Add to grocery cart" : "Out of stock"}
            </Text>
          </Pressable>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function CatalogMore({ catalog }: { catalog: { items: { id: number }[]; loading: boolean; loadingMore: boolean; hasNext: boolean; error: string; more: () => Promise<void>; refresh: () => Promise<void> } }) {
  if (catalog.loading) return null;
  return <View style={{ width: "100%", padding: 16 }}>
    {!!catalog.error && <Text accessibilityRole="alert" style={s.errorText}>{catalog.error}</Text>}
    {(catalog.hasNext || !!catalog.error) && <Pressable accessibilityRole="button" disabled={catalog.loadingMore}
      style={s.outline} onPress={() => void (catalog.items.length ? catalog.more() : catalog.refresh())}>
      {catalog.loadingMore ? <ActivityIndicator /> : <Text style={s.outlineText}>{catalog.error ? "Retry loading products" : "Load more products"}</Text>}
    </Pressable>}
  </View>;
}

function ZiyaApp() {
  const [tab, setTab] = useState<Tab>("Home");
  const [service, setService] = useState<Service>("shop");
  const [kidsGender, setKidsGender] = useState("");
  const [kidsAgeGroup, setKidsAgeGroup] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("newest");
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [filters, setFilters] = useState({
    subcategory: "",
    color: "",
    size: "",
    seller: "",
    min_price: "",
    max_price: "",
    rating: "",
  });
  const [filtersVisible, setFiltersVisible] = useState(false);
  const [recentlyViewed, setRecentlyViewed] = useState<Product[]>([]);
  const [selected, setSelected] = useState<Product | null>(null);
  const [selectedVariantId, setSelectedVariantId] = useState<number | null>(
    null,
  );
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [productLoading, setProductLoading] = useState(false);
  const images = useMemo(() => selected ? [
    selected.image_url,
    ...(selected.gallery || []),
    ...(selected.variants || []).flatMap(v => [v.color.image_url, v.image_url]),
  ].filter((url, index, all): url is string => !!url && all.indexOf(url) === index) : [], [selected]);
  const [productQuantity, setProductQuantity] = useState(1);
  const [imageZoomVisible, setImageZoomVisible] = useState(false);
  const [categories, setCategories] = useState<Category[]>([]);
  const [category, setCategory] = useState<Category | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const catalogParams = tab === "Search" ? { q: query, sort, ...filters } : {
    category: category?.slug,
    gender: category?.slug === "kids-wear" ? kidsGender : "",
    kids_age_group: category?.slug === "kids-wear" ? kidsAgeGroup : "",
  };
  const catalog = useCatalog<Product>(JSON.stringify([catalogParams, token]),
    (page, signal) => getProducts({ ...catalogParams, page: String(page) }, signal, token));
  const { items: products, setItems: setProducts, loading, error } = catalog;
  const [user, setUser] = useState<User | null>(null);
  const [authVisible, setAuthVisible] = useState(false);
  const [partnerMode, setPartnerMode] = useState<"seller" | "rider" | null>(null);
  const [accountTool, setAccountTool] = useState<"support" | "settings" | null>(null);
  const [accountView, setAccountView] = useState<
    "profile" | "orders" | "addresses" | "wishlist" | null
  >(null);
  const [cart, setCart] = useState<Cart>({
    items: [],
    item_count: 0,
    subtotal: "0",
  });
  const [foodCart, setFoodCart] = useState<FoodCartRow[]>([]);
  const [groceryCart, setGroceryCart] = useState<GroceryCartRow[]>([]);
  const [locationVisible, setLocationVisible] = useState(false);
  const [deliveryLocation, setDeliveryLocation] = useState(
    "Choose your location",
  );
  const [storageReady, setStorageReady] = useState(false);
  usePushRegistration(token);
  useEffect(() => { if (storageReady && !token) void stopTracking().catch(() => undefined); }, [token, storageReady]);
  const [inboxVisible, setInboxVisible] = useState(false);
  const [notificationOrder, setNotificationOrder] = useState<Order | null>(null);
  const [partnerTarget, setPartnerTarget] = useState<NotificationTarget | null>(null);
  const activeToken = useRef(token);
  activeToken.current = token;
  useEffect(() => { setNotificationOrder(null); setPartnerTarget(null); }, [token]);
  const openNotification = async (data: NotificationTarget = {}) => {
    if (!token) return;
    setInboxVisible(false);
    setPartnerTarget(data);
    if (data.target === "seller") { setPartnerMode("seller"); return; }
    if (data.target === "rider") { setPartnerMode("rider"); return; }
    if (data.order_id && ["shop", "food", "grocery"].includes(data.kind || "")) {
      try {
        const orders = await getOrders(token);
        if (activeToken.current !== token) return;
        const found = orders.find(o => o.id === data.order_id && o.kind === data.kind);
        if (found) setNotificationOrder(found);
      } catch (error: any) { Alert.alert("Could not open order", error.message); }
    }
  };
  useEffect(() => {
    // Android remote-notification listeners are unavailable in Expo Go (SDK 53+).
    if (!token || Constants.appOwnership === "expo") return;
    let cancelled = false;
    let subscription: { remove: () => void } | undefined;
    void import("expo-notifications").then(Notifications => {
      if (cancelled) return;
      subscription = Notifications.addNotificationResponseReceivedListener(response => { void openNotification(response.notification.request.content.data); });
      void Notifications.getLastNotificationResponseAsync().then(response => {
        if (response) { void openNotification(response.notification.request.content.data); void Notifications.clearLastNotificationResponseAsync(); }
      });
    }).catch(() => undefined);
    return () => { cancelled = true; subscription?.remove(); };
  }, [token]);
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null); setUser(null);
      setCart({ items: [], item_count: 0, subtotal: "0" });
      setFoodCart([]); setGroceryCart([]);
      SecureStore.deleteItemAsync("ziyamart_token");
      Alert.alert("Session expired", "Please sign in again to continue.");
      setAuthVisible(true);
    });
    return () => setUnauthorizedHandler(null);
  }, []);
  const load = catalog.refresh;
  useEffect(() => {
    let active = true;
    getCategories().then(groups => { if (active) setCategories(groups); }).catch(() => {});
    return () => { active = false; };
  }, []);
  useEffect(() => {
    Promise.all([
      SecureStore.getItemAsync("ziyamart_token"),
      AsyncStorage.getItem("ziyamart_token"),
    ]).then(async ([secureToken, legacyToken]) => {
      const saved = secureToken || legacyToken;
      if (!secureToken && legacyToken) {
        await SecureStore.setItemAsync("ziyamart_token", legacyToken);
        await AsyncStorage.removeItem("ziyamart_token");
      }
      if (saved) {
        setToken(saved);
        Promise.all([
          getCart(saved),
          getProfile(saved),
          getFoodCart(saved),
          getGroceryCart(saved),
        ])
          .then(([bag, profile, food, grocery]) => {
            setCart(bag);
            setUser(profile);
            setFoodCart(foodRows(food));
            setGroceryCart(groceryRows(grocery));
          })
          .catch(() => {
            setToken(null);
            SecureStore.deleteItemAsync("ziyamart_token");
            AsyncStorage.removeItem("ziyamart_token");
          });
      }
    });
  }, []);
  useEffect(() => {
    AsyncStorage.getItem("ziyamart_location")
      .then((location) => {
        if (location) setDeliveryLocation(location);
      })
      .catch(() => {})
      .finally(() => setStorageReady(true));
  }, []);
  useEffect(() => {
    AsyncStorage.getItem("ziyamart_recent_searches")
      .then((value) => value && setRecentSearches(JSON.parse(value)))
      .catch(() => {});
  }, []);
  useEffect(() => {
    AsyncStorage.getItem("ziyamart_recent_products")
      .then((value) => value && setRecentlyViewed(JSON.parse(value)))
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (storageReady)
      AsyncStorage.setItem("ziyamart_location", deliveryLocation).catch(
        () => {},
      );
  }, [deliveryLocation, storageReady]);
  // Search/filter matching is performed by the API across the full catalog.
  const visible = products;
  const count =
    cart.item_count +
    foodCart.reduce((n, row) => n + row.quantity, 0) +
    groceryCart.reduce((n, row) => n + row.quantity, 0);
  const authenticate = async (nextToken: string, nextUser: User) => {
    setToken(nextToken);
    setUser(nextUser);
    await SecureStore.setItemAsync("ziyamart_token", nextToken);
    const [shop, food, grocery] = await Promise.all([
      getCart(nextToken),
      getFoodCart(nextToken),
      getGroceryCart(nextToken),
    ]);
    setCart(shop);
    setFoodCart(foodRows(food));
    setGroceryCart(groceryRows(grocery));
  };
  const rememberSearch = (value: string) => {
    const clean = value.trim();
    if (!clean) return;
    const next = [
      clean,
      ...recentSearches.filter(
        (row) => row.toLowerCase() !== clean.toLowerCase(),
      ),
    ].slice(0, 6);
    setRecentSearches(next);
    AsyncStorage.setItem(
      "ziyamart_recent_searches",
      JSON.stringify(next),
    ).catch(() => {});
  };
  const openProduct = async (product: Product) => {
    if (productLoading) return;
    setProductLoading(true);
    const recent = [
      product,
      ...recentlyViewed.filter((row) => row.id !== product.id),
    ].slice(0, 8);
    setRecentlyViewed(recent);
    AsyncStorage.setItem(
      "ziyamart_recent_products",
      JSON.stringify(recent),
    ).catch(() => {});
    setProductQuantity(1);
    try {
      const detail = await getProduct(product.slug, token);
      setSelected(detail);
      const defaultVariant = detail.variants?.find(v => v.stock > 0) || detail.variants?.[0];
      setSelectedImage(defaultVariant?.image_url || defaultVariant?.color.image_url || detail.image_url);
      setSelectedVariantId(defaultVariant?.id ?? null);
    } catch {
      Alert.alert(
        "Could not load product",
        "Please check your connection and try again.",
      );
    } finally {
      setProductLoading(false);
    }
  };
  const toggleWishlist = async (product: Product) => {
    if (!token) {
      setAuthVisible(true);
      return;
    }
    try {
      if (product.is_wishlisted) await removeWishlist(token, product.id);
      else await addWishlist(token, product.id);
      setProducts((rows) =>
        rows.map((row) =>
          row.id === product.id
            ? { ...row, is_wishlisted: !product.is_wishlisted }
            : row,
        ),
      );
    } catch (error: any) {
      Alert.alert("Wishlist unavailable", error.message);
    }
  };
  const add = async (
    product: Product,
    variantId?: number,
    quantity = 1,
    goToCart = false,
  ) => {
    if (!token) {
      setAuthVisible(true);
      return;
    }
    const detail = product.variants
      ? product
      : await getProduct(product.slug, token);
    const variant =
      variantId || detail.variants?.find((row) => row.stock > 0)?.id;
    if (!variant) {
      Alert.alert("Unavailable", "Select an available color and size.");
      return;
    }
    try {
      await addCartItem(token, variant, quantity);
      setCart(await getCart(token));
      if (goToCart) {
        setSelected(null);
        setTab("Cart");
        return;
      }
      Alert.alert("Added to your Shop cart", product.name, [
        { text: "Continue shopping", style: "cancel" },
        {
          text: "View cart",
          onPress: () => {
            setSelected(null);
            setTab("Cart");
          },
        },
      ]);
    } catch (error: any) {
      Alert.alert("Could not add item", error.message);
    }
  };

  if (productLoading) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator size="large" color={C.green} />
          <Text style={s.helperText}>Loading product photos and options…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (selected) {
    const variants = selected.variants || [];
    const chosen = variants.find((v) => v.id === selectedVariantId);
    const colors = Array.from(
      new Map(variants.map((v) => [v.color.id, v.color])).values(),
    );
    const chosenColor = chosen?.color.id;
    const visibleSizes = variants;
    return (
      <SafeAreaView style={s.safe}>
        <StatusBar style="dark" />
        <ScrollView contentContainerStyle={s.detailPage}>
          <Pressable onPress={() => setSelected(null)} style={s.back}>
            <Text style={s.backText}>‹ Back</Text>
          </Pressable>
          {images.length ? (
            <Pressable
              style={s.detailImageWrap}
              accessibilityRole="button"
              accessibilityLabel="Enlarge product image"
              onPress={() => {
                setSelectedImage(selectedImage || images[0]);
                setImageZoomVisible(true);
              }}
            >
              <Image source={{ uri: selectedImage || images[0] }} style={s.detailImage} />
            </Pressable>
          ) : (
            <View style={s.detailImageWrap}>
              <Text style={s.detailPlaceholder}>ZIYAMART</Text>
            </View>
          )}
          {images.length > 0 && (
            <View style={s.thumbnails}>
              {images.map((url, index) => (
                <Pressable
                  key={url}
                  accessibilityRole="button"
                  accessibilityLabel={`View product image ${index + 1}`}
                  accessibilityState={{ selected: selectedImage === url }}
                  onPress={() => setSelectedImage(url)}
                  style={[
                    s.thumbWrap,
                    selectedImage === url && s.thumbSelected,
                  ]}
                >
                  <Image source={{ uri: url }} style={s.thumb} />
                </Pressable>
              ))}
            </View>
          )}
          <Text style={s.detailTitle}>{selected.name}</Text>
          <View style={s.ratingRow}>
            <Text style={s.stars}>
              {"★".repeat(Math.round(selected.rating || 0))}
              {"☆".repeat(5 - Math.round(selected.rating || 0))}
            </Text>
            <Text style={s.ratingCopy}>
              {Number(selected.rating || 0).toFixed(1)} / 5 (
              {selected.review_count || 0} Reviews)
            </Text>
          </View>
          <Text style={s.detailPrice}>
            {money(chosen?.price || selected.price)}
          </Text>
          <Text style={s.inclusive}>
            Inclusive of merchandise GST and platform-fee GST. Customer delivery
            charge: ₹0.
          </Text>
          <Text style={s.description}>
            {selected.description ||
              "A carefully selected product from ZIYAMART."}
          </Text>
          <View style={s.infoGrid}>
            <View style={s.infoHalf}>
              <Text style={s.infoLabel}>Sold by</Text>
              <Text style={s.infoValue}>
                {selected.seller_name || "ZIYAMART"}
              </Text>
            </View>
            <View style={s.infoHalf}>
              <Text style={s.infoLabel}>Category</Text>
              <Text style={s.infoValue}>
                {selected.category?.name || "General"}
              </Text>
            </View>
          </View>
          <View style={s.stockBanner}>
            <Text style={s.stockBannerText}>
              {chosen?.stock === 0
                ? "Currently unavailable"
                : chosen
                  ? `✓ ${chosen.stock} available`
                  : "Select a variant to check stock"}
            </Text>
          </View>
          <Text style={s.sectionTitle}>Choose Color</Text>
          <View style={s.colorRow}>
            {colors.map((color) => (
              <Pressable
                accessibilityLabel={`Select ${color.name}`}
                key={color.id}
                style={[
                  s.colorChoice,
                  chosenColor === color.id && s.optionSelected,
                ]}
                onPress={() => {
                  const first =
                    variants.find(
                      (v) => v.color.id === color.id && v.size === chosen?.size && v.stock > 0,
                    ) ||
                    variants.find(
                      (v) => v.color.id === color.id && v.stock > 0,
                    ) || variants.find((v) => v.color.id === color.id);
                  setSelectedVariantId(first?.id || null);
                  setSelectedImage(
                    first?.image_url || color.image_url || selected.image_url,
                  );
                  setProductQuantity(1);
                }}
              >
                <View
                  style={[s.bigSwatch, { backgroundColor: color.hex_code }]}
                />
                <Text style={s.colorName}>{color.name}</Text>
              </Pressable>
            ))}
          </View>
          <Text style={s.sectionTitle}>Choose Size</Text>
          <View style={s.sizeRow}>
            {visibleSizes.map((v) => (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`${v.color.name}, size ${v.size}${v.stock < 1 ? ", sold out" : ""}`}
                accessibilityState={{ selected: selectedVariantId === v.id, disabled: v.stock < 1 }}
                disabled={v.stock < 1}
                key={v.id}
                style={[
                  s.sizeChoice,
                  selectedVariantId === v.id && s.optionSelected,
                  v.stock < 1 && s.disabled,
                ]}
                onPress={() => {
                  setSelectedVariantId(v.id);
                  setProductQuantity(1);
                  setSelectedImage(v.image_url || v.color.image_url || selected.image_url || images[0] || null);
                }}
              >
                <Text
                  style={[
                    s.sizeText,
                    selectedVariantId === v.id && s.optionTextSelected,
                  ]}
                >
                  {v.color.name} · {v.size}
                  {v.stock < 1 ? " · Sold out" : ""}
                </Text>
              </Pressable>
            ))}
          </View>
          <Text style={s.sectionTitle}>Quantity</Text>
          <View style={s.qty}>
            <Pressable
              onPress={() =>
                setProductQuantity(Math.max(1, productQuantity - 1))
              }
            >
              <Text style={s.qtyBtn}>−</Text>
            </Pressable>
            <Text style={s.qtyValue}>{productQuantity}</Text>
            <Pressable
              disabled={
                !chosen || productQuantity >= Math.min(10, chosen.stock)
              }
              onPress={() =>
                setProductQuantity(
                  Math.min(10, chosen?.stock || 1, productQuantity + 1),
                )
              }
            >
              <Text style={s.qtyBtn}>＋</Text>
            </Pressable>
          </View>
          <Pressable
            disabled={!chosen || chosen.stock < 1}
            style={[s.primary, (!chosen || chosen.stock < 1) && s.disabled]}
            onPress={() => chosen && add(selected, chosen.id, productQuantity)}
          >
            <Text style={s.primaryText}>
              {chosen
                ? `🛒 Add ${productQuantity} · ${money(String(Number(chosen.price) * productQuantity))}`
                : "Select color and size"}
            </Text>
          </Pressable>
          <Pressable
            disabled={!chosen || chosen.stock < 1}
            style={[s.outline, (!chosen || chosen.stock < 1) && s.disabled]}
            onPress={() =>
              chosen && add(selected, chosen.id, productQuantity, true)
            }
          >
            <Text style={s.outlineText}>Buy now</Text>
          </Pressable>
          <Pressable
            style={s.outline}
            onPress={() =>
              Share.share({
                message: `${selected.name}\n${selected.description}\nhttps://ziyamart.in/products/${selected.slug}/`,
              })
            }
          >
            <Text style={s.outlineText}>Share product</Text>
          </Pressable>
          <Pressable
            style={s.wishlistWide}
            onPress={async () => {
              if (!token) {
                setSelected(null);
                setAuthVisible(true);
                return;
              }
              if (selected.is_wishlisted)
                await removeWishlist(token, selected.id);
              else await addWishlist(token, selected.id);
              setSelected({
                ...selected,
                is_wishlisted: !selected.is_wishlisted,
              });
            }}
          >
            <Text style={s.viewDetails}>
              {selected.is_wishlisted
                ? "♥ Remove from Wishlist"
                : "♡ Save to Wishlist"}
            </Text>
          </Pressable>
          <View style={s.benefits}>
            <View style={s.benefit}>
              <Text style={s.benefitIcon}>🚚</Text>
              <Text style={s.benefitTitle}>₹0 Customer Delivery</Text>
              <Text style={s.benefitCopy}>Seller-sponsored</Text>
            </View>
            <View style={s.benefit}>
              <Text style={s.benefitIcon}>🔄</Text>
              <Text style={s.benefitTitle}>Easy Returns</Text>
              <Text style={s.benefitCopy}>7-day return</Text>
            </View>
            <View style={s.benefit}>
              <Text style={s.benefitIcon}>🔒</Text>
              <Text style={s.benefitTitle}>Secure Payment</Text>
              <Text style={s.benefitCopy}>100% protected</Text>
            </View>
          </View>
          <Text style={s.sectionTitle}>Product Description</Text>
          <View style={s.descriptionBox}>
            <Text style={s.description}>
              {selected.description || "Product details will be added soon."}
            </Text>
          </View>
          {!!selected.specifications && (
            <>
              <Text style={s.sectionTitle}>Specifications</Text>
              <View style={s.descriptionBox}>
                {Object.entries(selected.specifications)
                  .filter(([, value]) => !!value)
                  .map(([label, value]) => (
                    <View key={label} style={s.specRow}>
                      <Text style={s.storeMeta}>
                        {label.replaceAll("_", " ")}
                      </Text>
                      <Text style={s.infoValue}>{value}</Text>
                    </View>
                  ))}
              </View>
            </>
          )}
          {!!selected.reviews?.length && (
            <>
              <Text style={s.sectionTitle}>Customer reviews</Text>
              {selected.reviews.map((review) => (
                <View key={review.id} style={s.listCard}>
                  <Text style={s.stars}>
                    {"★".repeat(review.rating)}
                    {"☆".repeat(5 - review.rating)}
                  </Text>
                  <Text style={s.listTitle}>
                    {review.title || review.username}
                  </Text>
                  <Text style={s.description}>{review.review}</Text>
                  <Text style={s.storeMeta}>
                    {review.username}
                    {review.verified ? " · Verified purchase" : ""}
                  </Text>
                </View>
              ))}
            </>
          )}
          {products.some(
            (row) =>
              row.id !== selected.id &&
              row.category?.id === selected.category?.id,
          ) && (
            <>
              <Text style={s.sectionTitle}>You may also like</Text>
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={s.relatedRow}
              >
                {products
                  .filter(
                    (row) =>
                      row.id !== selected.id &&
                      row.category?.id === selected.category?.id,
                  )
                  .slice(0, 6)
                  .map((row) => (
                    <ProductCard
                      key={row.id}
                      product={row}
                      onOpen={() => openProduct(row)}
                      onWishlist={() => toggleWishlist(row)}
                    />
                  ))}
              </ScrollView>
            </>
          )}
        </ScrollView>
        <Modal
          visible={imageZoomVisible}
          transparent
          animationType="fade"
          onRequestClose={() => setImageZoomVisible(false)}
        >
          <Pressable
            style={s.zoomBackdrop}
            onPress={() => setImageZoomVisible(false)}
          >
            {selectedImage && (
              <Image source={{ uri: selectedImage }} style={s.zoomImage} />
            )}
            <Text style={s.zoomClose}>Tap to close</Text>
          </Pressable>
        </Modal>
        <AuthModal
          visible={authVisible}
          onClose={() => setAuthVisible(false)}
          onAuthenticated={authenticate}
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <StatusBar style="dark" />
      <Header
        count={count}
        location={deliveryLocation}
        onLocation={() => setLocationVisible(true)}
        onCart={() => setTab("Cart")}
        onLogo={() => {
          setService("shop");
          setTab("Home");
        }}
      />
      <ServiceStrip
        selected={service}
        onSelect={(value) => {
          setService(value);
          setTab("Home");
        }}
      />
      <View style={s.body}>
        {tab === "Home" && service !== "shop" && (
          <LocalServiceScreen
            service={service}
            pincode={deliveryLocation.match(/\b\d{6}\b/)?.[0] || ""}
            token={token}
            onLogin={() => setAuthVisible(true)}
            foodCart={foodCart}
            setFoodCart={setFoodCart}
            groceryCart={groceryCart}
            setGroceryCart={setGroceryCart}
            onOpenCart={() => setTab("Cart")}
          />
        )}
        {tab === "Home" && service === "shop" && (
          <ScrollView
            showsVerticalScrollIndicator={false}
            contentContainerStyle={s.page}
          >
            <LinearGradient colors={["#ECFAF4", "#D7F4E6"]} style={s.hero}>
              <View style={s.heroCopy}>
                <Text style={s.heroKicker}>QUALITY · VARIETY · VALUE</Text>
                <Text style={s.heroTitle}>
                  Everything you love,{`\n`}all in one place.
                </Text>
                <Pressable
                  style={s.shopButton}
                  onPress={() => setTab("Search")}
                >
                  <Text style={s.shopText}>Shop now →</Text>
                </Pressable>
              </View>
              <View style={s.heroOrb}>
                <Image source={BRAND_MARK} style={s.heroBrand} />
              </View>
            </LinearGradient>
            <View style={s.sectionRow}>
              <Text style={s.heading}>Shop by category</Text>

              <Pressable onPress={() => setTab("Categories")}>
                <Text style={s.link}>See all →</Text>
              </Pressable>
            </View>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={s.categories}
            >
              <Pressable style={s.category} onPress={() => setCategory(null)}>
                <View style={[s.categoryIcon, !category && s.categorySelected]}>
                  <Text style={s.categoryEmoji}>✨</Text>
                </View>
                <Text style={s.categoryLabel}>All</Text>
              </Pressable>
              {categories.map((group) => (
                <Pressable
                  key={group.id}
                  style={s.category}
                  onPress={() => setCategory(group)}
                >
                  <View
                    style={[
                      s.categoryIcon,
                      category?.id === group.id && s.categorySelected,
                    ]}
                  >
                    {group.image_url ? (
                      <Image
                        source={{ uri: group.image_url }}
                        style={s.categoryImage}
                      />
                    ) : (
                      <Text style={s.categoryEmoji}>🛍️</Text>
                    )}
                  </View>
                  <Text style={s.categoryLabel} numberOfLines={1}>
                    {group.name}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
            <View style={s.sectionRow}>
              <Text style={s.heading}>Fresh picks for you</Text>
              <Text style={s.link}>Explore</Text>
            </View>
            {loading ? (
              <ActivityIndicator
                color={C.orange}
                size="large"
                style={s.loader}
              />
            ) : error ? (
              <View style={s.errorBox}>
                <Text style={s.errorText}>{error}</Text>
                <Pressable onPress={load}>
                  <Text style={s.retry}>Try again</Text>
                </Pressable>
              </View>
            ) : (
              <View style={s.grid}>
                {products.slice(0, 10).map((p) => (
                  <ProductCard
                    key={p.id}
                    product={p}
                    onOpen={() => openProduct(p)}
                    onWishlist={() => toggleWishlist(p)}
                  />
                ))}
              </View>
            )}
            {!!recentlyViewed.length && (
              <>
                <View style={s.sectionRow}>
                  <Text style={s.heading}>Recently viewed</Text>
                </View>
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  contentContainerStyle={s.relatedRow}
                >
                  {recentlyViewed.map((row) => (
                    <ProductCard
                      key={row.id}
                      product={row}
                      onOpen={() => openProduct(row)}
                      onWishlist={() => toggleWishlist(row)}
                    />
                  ))}
                </ScrollView>
              </>
            )}
          </ScrollView>
        )}

        {/* ========================= */}
        {/* ALL CATEGORIES PAGE */}
        {/* ========================= */}
        {tab === "Categories" && service === "shop" && (
          <ScrollView
            showsVerticalScrollIndicator={false}
            contentContainerStyle={s.page}
          >
            {/* ================================= */}
            {/* KIDS WEAR - GENDER SELECTION */}
            {/* ================================= */}
            {category?.slug === "kids-wear" ? (
              <>
                <View style={s.sectionRow}>
                  <Pressable
                    onPress={() => {
                      setCategory(null);
                      setKidsGender("");
                      setKidsAgeGroup("");
                    }}
                  >
                    <Text style={s.link}>← Categories</Text>
                  </Pressable>

                  <Text style={s.pageTitle}>Kids' Wear</Text>
                </View>

                <Text style={s.heading}>
                  Who are you shopping for?
                </Text>

                <Text
                  style={{
                    marginTop: 6,
                    marginBottom: 20,
                    color: "#6B7280",
                    fontSize: 14,
                  }}
                >
                  Select a gender to continue
                </Text>

                <View style={s.categoriesGrid}>
                  <Pressable
                    style={s.categoryGridItem}
                    onPress={() => {
                      setKidsGender("male");
                      setKidsAgeGroup("");
                    }}
                  >
                    <View
                      style={[
                        s.categoryIcon,
                        kidsGender === "male" && s.categorySelected,
                      ]}
                    >
                      <Text style={s.categoryEmoji}>👦</Text>
                    </View>

                    <Text style={s.categoryLabel}>Boys</Text>
                  </Pressable>

                  <Pressable
                    style={s.categoryGridItem}
                    onPress={() => {
                      setKidsGender("female");
                      setKidsAgeGroup("");
                    }}
                  >
                    <View
                      style={[
                        s.categoryIcon,
                        kidsGender === "female" && s.categorySelected,
                      ]}
                    >
                      <Text style={s.categoryEmoji}>👧</Text>
                    </View>

                    <Text style={s.categoryLabel}>Girls</Text>
                  </Pressable>

                  <Pressable
                    style={s.categoryGridItem}
                    onPress={() => {
                      setKidsGender("unisex");
                      setKidsAgeGroup("");
                    }}
                  >
                    <View
                      style={[
                        s.categoryIcon,
                        kidsGender === "unisex" && s.categorySelected,
                      ]}
                    >
                      <Text style={s.categoryEmoji}>🧒</Text>
                    </View>

                    <Text style={s.categoryLabel}>Unisex</Text>
                  </Pressable>
                </View>
                                {/* AGE SELECTION */}
                {kidsGender !== "" && (
                  <>
                    <Text
                      style={[
                        s.heading,
                        {
                          marginTop: 28,
                        },
                      ]}
                    >
                      Select age
                    </Text>

                    <Text
                      style={{
                        marginTop: 6,
                        marginBottom: 16,
                        color: "#6B7280",
                        fontSize: 14,
                      }}
                    >
                      Choose the child's age group
                    </Text>

                    <View
                      style={{
                        flexDirection: "row",
                        flexWrap: "wrap",
                        gap: 10,
                      }}
                    >
                      {[
                        ["0-1", "0–1 Year"],
                        ["1-2", "1–2 Years"],
                        ["2-4", "2–4 Years"],
                        ["4-6", "4–6 Years"],
                        ["6-8", "6–8 Years"],
                        ["8-10", "8–10 Years"],
                        ["10-12", "10–12 Years"],
                        ["12-14", "12–14 Years"],
                      ].map(([value, label]) => (
                        <Pressable
                          key={value}
                          onPress={() => setKidsAgeGroup(value)}
                          style={[
                            {
                              paddingVertical: 12,
                              paddingHorizontal: 16,
                              borderRadius: 14,
                              backgroundColor: "#F3F4F6",
                              borderWidth: 1,
                              borderColor: "#E5E7EB",
                            },
                            kidsAgeGroup === value && {
                              borderColor: C.orange,
                              backgroundColor: "#FFF7ED",
                            },
                          ]}
                        >
                          <Text
                            style={{
                              fontSize: 14,
                              fontWeight: "700",
                              color:
                                kidsAgeGroup === value
                                  ? C.orange
                                  : C.ink,
                            }}
                          >
                            {label}
                          </Text>
                        </Pressable>
                      ))}
                    </View>
                  </>
                )}
                                {/* MATCHING KIDS PRODUCTS */}
                {kidsGender !== "" && kidsAgeGroup !== "" && (
                  <>
                    <View
                      style={[
                        s.sectionRow,
                        {
                          marginTop: 30,
                        },
                      ]}
                    >
                      <Text style={s.heading}>Matching products</Text>

                      <Text style={s.link}>
                        {catalog.count} found
                      </Text>
                    </View>

                    {loading ? (
                      <ActivityIndicator
                        size="large"
                        color={C.orange}
                        style={{ marginTop: 30 }}
                      />
                    ) : error && products.length === 0 ? (
                      <View style={s.errorBox}>
                        <Text style={s.errorText}>{error}</Text>

                        <Pressable onPress={load}>
                          <Text style={s.retry}>Try again</Text>
                        </Pressable>
                      </View>
                    ) : products.length === 0 ? (
                      <View
                        style={{
                          paddingVertical: 40,
                          alignItems: "center",
                        }}
                      >
                        <Text style={{ fontSize: 36 }}>🛍️</Text>

                        <Text
                          style={[
                            s.heading,
                            {
                              marginTop: 12,
                              textAlign: "center",
                            },
                          ]}
                        >
                          No products found
                        </Text>

                        <Text
                          style={{
                            marginTop: 7,
                            color: "#6B7280",
                            fontSize: 14,
                            textAlign: "center",
                          }}
                        >
                          Try another gender or age group.
                        </Text>
                      </View>
                    ) : (
                      <View style={s.grid}>
                        {products.map((product) => (
                          <ProductCard
                            key={product.id}
                            product={product}
                            onOpen={() => openProduct(product)}
                            onWishlist={() => toggleWishlist(product)}
                          />
                        ))}
                        <CatalogMore catalog={catalog} />
                      </View>
                    )}
                  </>
                )}
              </>
            ) : (
              <>
                {/* ================================= */}
                {/* ALL CATEGORIES */}
                {/* ================================= */}

                <View style={s.sectionRow}>
                  <Pressable onPress={() => setTab("Home")}>
                    <Text style={s.link}>← Back</Text>
                  </Pressable>

                  <Text style={s.pageTitle}>All Categories</Text>
                </View>

                <Text
                  style={{
                    marginBottom: 18,
                    color: "#6B7280",
                    fontSize: 14,
                  }}
                >
                  Select a category to start shopping
                </Text>

                <View style={s.categoriesGrid}>
                  {/* ALL */}
                  <Pressable
                    style={s.categoryGridItem}
                    onPress={() => {
                      setCategory(null);
                      setKidsGender("");
                      setKidsAgeGroup("");
                    }}
                  >
                    <View
                      style={[
                        s.categoryIcon,
                        !category && s.categorySelected,
                      ]}
                    >
                      <Text style={s.categoryEmoji}>✨</Text>
                    </View>

                    <Text style={s.categoryLabel}>All</Text>
                  </Pressable>

                  {/* AVAILABLE CATEGORIES */}
                  {categories.map((group) => (
                    <Pressable
                      key={group.id}
                      style={s.categoryGridItem}
                      onPress={() => {
                        setKidsGender("");
                        setKidsAgeGroup("");
                        setCategory(group);
                      }}
                    >
                      <View
                        style={[
                          s.categoryIcon,
                          category?.id === group.id &&
                            s.categorySelected,
                        ]}
                      >
                        {group.image_url ? (
                          <Image
                            source={{ uri: group.image_url }}
                            style={s.categoryImage}
                          />
                        ) : (
                          <Text style={s.categoryEmoji}>🛍️</Text>
                        )}
                      </View>

                      <Text
                        style={s.categoryLabel}
                        numberOfLines={2}
                      >
                        {group.name}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              </>
            )}
          </ScrollView>
        )}

        {/* ========================= */}
        {/* SEARCH PAGE */}
        {/* ========================= */}
        {tab === "Search" && (
          <View style={s.searchPage}>
            <Text style={s.pageTitle}>Find something special</Text>
            <View style={s.searchToolbar}>
              <TextInput
                value={query}
                onChangeText={setQuery}
                onSubmitEditing={() => rememberSearch(query)}
                autoFocus
                placeholder="Search products"
                placeholderTextColor="#9AA4B2"
                style={[s.searchInput, s.searchGrow]}
              />
              <Pressable
                style={s.filterButton}
                onPress={() => setFiltersVisible(true)}
              >
                <Text style={s.filterButtonText}>Filters</Text>
              </Pressable>
            </View>
            {!query && !!recentSearches.length && (
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={s.filterChips}
              >
                {recentSearches.map((row) => (
                  <Pressable
                    key={row}
                    style={s.filterChip}
                    onPress={() => setQuery(row)}
                  >
                    <Text>↺ {row}</Text>
                  </Pressable>
                ))}
              </ScrollView>
            )}
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={s.filterChips}
            >
              {[
                ["newest", "Newest"],
                ["popularity", "Popular"],
                ["rating", "Top rated"],
                ["price_low", "Price ↑"],
                ["price_high", "Price ↓"],
              ].map(([value, label]) => (
                <Pressable
                  key={value}
                  style={[s.filterChip, sort === value && s.filterChipActive]}
                  onPress={() => setSort(value)}
                >
                  <Text>{label}</Text>
                </Pressable>
              ))}
            </ScrollView>
            {loading ? (
              <ActivityIndicator color={C.orange} />
            ) : (
              <ScrollView contentContainerStyle={s.grid}>
                {visible.map((p) => (
                  <ProductCard
                    key={p.id}
                    product={p}
                    onOpen={() => {
                      rememberSearch(query);
                      openProduct(p);
                    }}
                    onWishlist={() => toggleWishlist(p)}
                  />
                ))}
                <CatalogMore catalog={catalog} />
                {!error && !visible.length && <Text style={s.emptyCopy}>No products match your search.</Text>}
              </ScrollView>
            )}
            <FilterModal
              visible={filtersVisible}
              filters={filters}
              categories={categories}
              onApply={(value) => {
                setFilters(value);
                setFiltersVisible(false);
              }}
              onClose={() => setFiltersVisible(false)}
            />
          </View>
        )}
        {tab === "Cart" && (
          <CartHub
            cart={cart}
            token={token}
            onLogin={() => setAuthVisible(true)}
            onShopChanged={setCart}
            foodCart={foodCart}
            setFoodCart={setFoodCart}
            groceryCart={groceryCart}
            setGroceryCart={setGroceryCart}
            onBrowse={(next) => {
              setService(next);
              setTab("Home");
            }}
          />
        )}
        {tab === "Account" && (
          <ScrollView contentContainerStyle={s.accountPage}>
            <View style={s.avatar}>
              <Text style={s.avatarText}>
                {user?.username?.[0]?.toUpperCase() || "Z"}
              </Text>
            </View>
            <Text style={s.pageTitle}>
              {user
                ? `Hi, ${user.first_name || user.username}`
                : "Welcome to ZIYAMART"}
            </Text>
            <Text style={s.emptyCopy}>
              {user
                ? user.email
                : "Sign in to see orders, saved addresses, returns and support."}
            </Text>
            {!user ? (
              <Pressable style={s.primary} onPress={() => setAuthVisible(true)}>
                <Text style={s.primaryText}>Sign in or create account</Text>
              </Pressable>
            ) : (
              <Pressable
                style={s.outline}
                onPress={async () => {
                  try { await logout(token!); } catch (_) { /* Clear this device even if the network is unavailable. */ }
                  setToken(null);
                  setUser(null);
                  setCart({ items: [], item_count: 0, subtotal: "0" });
                  setFoodCart([]);
                  setGroceryCart([]);
                  await SecureStore.deleteItemAsync("ziyamart_token");
                }}
              >
                <Text style={s.outlineText}>Sign out</Text>
              </Pressable>
            )}
            {user && <View style={s.menuItem}>
              <Pressable accessibilityRole="button" onPress={() => setPartnerMode("seller")}><Text style={s.menuText}>Seller Center →</Text></Pressable>
              <Pressable accessibilityRole="button" onPress={() => setPartnerMode("rider")}><Text style={s.menuText}>Rider workspace →</Text></Pressable>
            </View>}
            {[
              ["Personal details", "profile"],
              ["My orders", "orders"],
              ["Saved addresses", "addresses"],
              ["Wishlist", "wishlist"],
            ].map(([item, view]) => (
              <Pressable
                key={item}
                style={s.menuItem}
                onPress={() =>
                  user ? setAccountView(view as any) : setAuthVisible(true)
                }
              >
                <Text style={s.menuText}>{item}</Text>
                <Text>›</Text>
              </Pressable>
            ))}
            <Pressable
              style={s.menuItem}
              onPress={() => user ? setAccountTool("support") : setAuthVisible(true)}
            >
              <Text style={s.menuText}>Help & support</Text>
              <Text>›</Text>
            </Pressable>
            {user && <Pressable accessibilityRole="button" style={s.menuItem} onPress={() => setInboxVisible(true)}><Text style={s.menuText}>Notifications →</Text></Pressable>}
            <Pressable style={s.menuItem} onPress={() => user ? setAccountTool("settings") : setAuthVisible(true)}>
              <Text style={s.menuText}>Account settings</Text><Text>›</Text>
            </Pressable>
          </ScrollView>
        )}
      </View>
      <View style={s.nav}>
        {(["Home", "Search", "Cart", "Account"] as Tab[]).map((item) => (
          <Pressable key={item} onPress={() => setTab(item)} style={s.navItem}>
            <Text style={[s.navIcon, tab === item && s.navActive]}>
              {item === "Home"
                ? "⌂"
                : item === "Search"
                  ? "⌕"
                  : item === "Cart"
                    ? "▱"
                    : "◯"}
            </Text>
            <Text style={[s.navLabel, tab === item && s.navActive]}>
              {item}
            </Text>
          </Pressable>
        ))}
      </View>
      <AuthModal
        visible={authVisible}
        onClose={() => setAuthVisible(false)}
        onAuthenticated={authenticate}
      />
      {token && partnerMode && <PartnerWorkspace key={`${token}-${partnerMode}-${partnerTarget?.order_id}-${partnerTarget?.delivery_id}`} token={token} mode={partnerMode} target={partnerTarget} onClose={() => { setPartnerMode(null); setPartnerTarget(null); }} />}
      {token && inboxVisible && <NotificationInbox token={token} onOpen={openNotification} onClose={() => setInboxVisible(false)} />}
      {token && notificationOrder && <OrderDetailModal token={token} order={notificationOrder} onClose={() => setNotificationOrder(null)} onChanged={async () => { const rows = await getOrders(token); setNotificationOrder(rows.find(o => o.id === notificationOrder.id && o.kind === notificationOrder.kind) || null); }} />}
      {token && accountTool && <AccountTools key={`${token}-${accountTool}`} token={token} mode={accountTool} onClose={() => setAccountTool(null)} onSignedOut={() => {
        setAccountTool(null); setAccountView(null); setPartnerMode(null); setToken(null); setUser(null);
        setCart({ items: [], item_count: 0, subtotal: "0" }); setFoodCart([]); setGroceryCart([]);
        SecureStore.deleteItemAsync("ziyamart_token"); setAuthVisible(true);
      }} />}
      <LocationModal
        visible={locationVisible}
        token={token}
        current={deliveryLocation}
        onClose={() => setLocationVisible(false)}
        onSelect={setDeliveryLocation}
      />
      {token && (
        <AccountSectionModal
          view={accountView}
          token={token}
          onClose={() => setAccountView(null)}
          onOpenProduct={(product) => {
            setAccountView(null);
            openProduct(product);
          }}
        />
      )}
    </SafeAreaView>
  );
}

function FilterModal({
  visible,
  filters,
  categories,
  onApply,
  onClose,
}: {
  visible: boolean;
  filters: {
    subcategory: string;
    color: string;
    size: string;
    seller: string;
    min_price: string;
    max_price: string;
    rating: string;
  };
  categories: Category[];
  onApply: (value: typeof filters) => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState(filters);
  useEffect(() => setForm(filters), [visible]);
  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={s.authPage} edges={["top", "bottom"]}>
        <View style={s.modalHeader}>
          <View>
            <Text style={s.modalTitle}>Filter products</Text>
            <Text style={s.checkoutStep}>REFINE YOUR RESULTS</Text>
          </View>
          <Pressable onPress={onClose}>
            <Text style={s.close}>×</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={s.modalContent}>
          <Text style={s.sectionTitle}>Price range</Text>
          <View style={s.filterFields}>
            <View style={s.listGrow}>
              <Field
                label="Minimum price"
                value={form.min_price}
                onChange={(value) =>
                  setForm({ ...form, min_price: value.replace(/\D/g, "") })
                }
                keyboard="number-pad"
              />
            </View>
            <View style={s.listGrow}>
              <Field
                label="Maximum price"
                value={form.max_price}
                onChange={(value) =>
                  setForm({ ...form, max_price: value.replace(/\D/g, "") })
                }
                keyboard="number-pad"
              />
            </View>
          </View>
          <Field
            label="Colour"
            value={form.color}
            onChange={(value) => setForm({ ...form, color: value })}
          />
          <Field
            label="Size"
            value={form.size}
            onChange={(value) => setForm({ ...form, size: value })}
          />
          <Field
            label="Seller or store"
            value={form.seller}
            onChange={(value) => setForm({ ...form, seller: value })}
          />
          <Text style={s.sectionTitle}>Minimum rating</Text>
          <View style={s.filterChips}>
            {["", "3", "4"].map((value) => (
              <Pressable
                key={value || "all"}
                style={[
                  s.filterChip,
                  form.rating === value && s.filterChipActive,
                ]}
                onPress={() => setForm({ ...form, rating: value })}
              >
                <Text>{value ? `${value}★ & above` : "Any rating"}</Text>
              </Pressable>
            ))}
          </View>
          <Text style={s.sectionTitle}>Subcategory</Text>
          <View style={s.colorRow}>
            <Pressable
              style={[s.filterChip, !form.subcategory && s.filterChipActive]}
              onPress={() => setForm({ ...form, subcategory: "" })}
            >
              <Text>All</Text>
            </Pressable>
            {categories
              .flatMap((row) => row.subcategories || [])
              .map((row) => (
                <Pressable
                  key={row.id}
                  style={[
                    s.filterChip,
                    form.subcategory === String(row.id) && s.filterChipActive,
                  ]}
                  onPress={() =>
                    setForm({ ...form, subcategory: String(row.id) })
                  }
                >
                  <Text>{row.name}</Text>
                </Pressable>
              ))}
          </View>
          <Pressable style={s.primary} onPress={() => onApply(form)}>
            <Text style={s.primaryText}>Apply filters</Text>
          </Pressable>
          <Pressable
            style={s.outline}
            onPress={() => {
              const empty = {
                subcategory: "",
                color: "",
                size: "",
                seller: "",
                min_price: "",
                max_price: "",
                rating: "",
              };
              setForm(empty);
              onApply(empty);
            }}
          >
            <Text style={s.outlineText}>Clear all filters</Text>
          </Pressable>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function LocationModal({
  visible,
  token,
  current,
  onClose,
  onSelect,
}: {
  visible: boolean;
  token: string | null;
  current: string;
  onClose: () => void;
  onSelect: (label: string) => void;
}) {
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [pincode, setPincode] = useState("");
  useEffect(() => {
    if (visible && token)
      getAddresses(token)
        .then(setAddresses)
        .catch(() => setAddresses([]));
  }, [visible, token]);
  const choose = (label: string) => {
    onSelect(label);
    onClose();
  };
  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={s.authPage} edges={["top", "bottom"]}>
        <View style={s.modalHeader}>
          <View>
            <Text style={s.modalTitle}>Delivery location</Text>
            <Text style={s.checkoutStep}>USED FOR AVAILABILITY & DELIVERY</Text>
          </View>
          <Pressable onPress={onClose}>
            <Text style={s.close}>×</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={s.modalContent}>
          <View style={s.currentLocation}>
            <Text style={s.locationPin}>⌖</Text>
            <View>
              <Text style={s.infoLabel}>CURRENT SELECTION</Text>
              <Text style={s.listTitle}>{current}</Text>
            </View>
          </View>
          {addresses.length > 0 && (
            <>
              <Text style={s.sectionTitle}>Saved addresses</Text>
              {addresses.map((address) => (
                <Pressable
                  key={address.id}
                  style={s.addressChoice}
                  onPress={() =>
                    choose(`${address.address_type} · ${address.pincode}`)
                  }
                >
                  <Text style={s.addressIcon}>
                    {address.address_type === "Home" ? "⌂" : "⌖"}
                  </Text>
                  <View style={s.listGrow}>
                    <Text style={s.listTitle}>
                      {address.address_type}
                      {address.is_default ? " · Default" : ""}
                    </Text>
                    <Text style={s.addressText}>
                      {address.address_line_1}, {address.city}, {address.state}{" "}
                      {address.pincode}
                    </Text>
                  </View>
                  <Text style={s.chevron}>›</Text>
                </Pressable>
              ))}
            </>
          )}
          <Text style={s.sectionTitle}>Enter another pincode</Text>
          <Text style={s.helperText}>
            See products and local services available near you.
          </Text>
          <TextInput
            value={pincode}
            onChangeText={(value) =>
              setPincode(value.replace(/\D/g, "").slice(0, 6))
            }
            keyboardType="number-pad"
            placeholder="6-digit delivery pincode"
            style={s.locationInput}
          />
          <Pressable
            disabled={pincode.length !== 6}
            style={[s.primary, pincode.length !== 6 && s.disabled]}
            onPress={() => choose(`Pincode ${pincode}`)}
          >
            <Text style={s.primaryText}>Use this location</Text>
          </Pressable>
          {!token && (
            <Text style={s.secureNote}>
              Sign in to use your saved delivery addresses across devices.
            </Text>
          )}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function CartHub({
  cart,
  token,
  onLogin,
  onShopChanged,
  foodCart,
  setFoodCart,
  groceryCart,
  setGroceryCart,
  onBrowse,
}: {
  cart: Cart;
  token: string | null;
  onLogin: () => void;
  onShopChanged: (cart: Cart) => void;
  foodCart: FoodCartRow[];
  setFoodCart: React.Dispatch<React.SetStateAction<FoodCartRow[]>>;
  groceryCart: GroceryCartRow[];
  setGroceryCart: React.Dispatch<React.SetStateAction<GroceryCartRow[]>>;
  onBrowse: (service: Service) => void;
}) {
  const [active, setActive] = useState<Service>("shop");
  const [checkout, setCheckout] = useState(false);
  const totals = {
    shop: Number(cart.subtotal),
    food: foodCart.reduce(
      (sum, row) =>
        sum +
        Number(
          row.item.options.find((o) => o.id === row.option_id)?.price || 0,
        ) *
          row.quantity,
      0,
    ),
    grocery: groceryCart.reduce(
      (sum, row) => sum + Number(row.product.price) * row.quantity,
      0,
    ),
  };
  const counts = {
    shop: cart.item_count,
    food: foodCart.reduce((n, row) => n + row.quantity, 0),
    grocery: groceryCart.reduce((n, row) => n + row.quantity, 0),
  };
  const checkoutItems =
    active === "shop"
      ? cart.items.map((row) => ({
          name: row.product.name,
          meta: `${row.variant?.color.name} · ${row.variant?.size}`,
          image_url: row.product.image_url,
          price: String(Number(row.total) / row.quantity),
          quantity: row.quantity,
        }))
      : active === "food"
        ? foodCart.map((row) => ({
            name: row.item.name,
            meta: row.option_name,
            image_url: row.item.image_url,
            price:
              row.item.options.find((o) => o.id === row.option_id)?.price ||
              "0",
            quantity: row.quantity,
          }))
        : groceryCart.map((row) => ({
            name: row.product.name,
            meta: row.product.unit,
            image_url: row.product.image_url,
            price: row.product.price,
            quantity: row.quantity,
          }));
  const place = (
    address: number,
    preferences: any,
    quoteId: string,
    idempotencyKey: string,
  ) =>
    active === "shop"
      ? checkoutShop(token!, address, quoteId, idempotencyKey, preferences?.payment_method)
      : active === "food"
        ? checkoutFood(
            token!,
            address,
            foodCart.map((row) => ({
              option_id: row.option_id,
              quantity: row.quantity,
              note: row.note,
            })),
            preferences?.include_cutlery,
            preferences?.delivery_note,
            quoteId,
            idempotencyKey,
            preferences?.payment_method,
          )
        : checkoutGrocery(
            token!,
            address,
            groceryCart.map((row) => ({
              product_id: row.product.id,
              quantity: row.quantity,
            })),
            preferences?.substitution_preference,
            quoteId,
            idempotencyKey,
            preferences?.payment_method,
          );
  const completed = async () => {
    if (active === "shop") onShopChanged(await getCart(token!));
    if (active === "food") setFoodCart(foodRows(await getFoodCart(token!)));
    if (active === "grocery")
      setGroceryCart(groceryRows(await getGroceryCart(token!)));
  };
  const updateFood = async (id: number, delta: number) => {
    if (!token) return onLogin();
    const row = foodCart.find((item) => item.option_id === id);
    if (!row) return;
    if (row.quantity + delta < 1) {
      return Alert.alert("Remove food item?", row.item.name, [
        { text: "Keep", style: "cancel" },
        {
          text: "Remove",
          style: "destructive",
          onPress: async () => {
            setFoodCart(foodRows(await deleteFoodCartItem(token, row.id)));
            Alert.alert("Item removed", row.item.name, [
              { text: "Done", style: "cancel" },
              {
                text: "Undo",
                onPress: async () =>
                  setFoodCart(
                    foodRows(
                      await addFoodCartItem(
                        token,
                        row.option_id,
                        false,
                        row.quantity,
                        row.note,
                      ),
                    ),
                  ),
              },
            ]);
          },
        },
      ]);
    }
    try {
      const result = await updateFoodCartItem(
        token,
        row.id,
        row.quantity + delta,
      );
      setFoodCart(foodRows(result));
    } catch (error: any) {
      Alert.alert("Could not update cart", error.message);
    }
  };
  const updateGrocery = async (id: number, delta: number) => {
    if (!token) return onLogin();
    const row = groceryCart.find((item) => item.product.id === id);
    if (!row) return;
    if (row.quantity + delta < 1) {
      return Alert.alert("Remove grocery item?", row.product.name, [
        { text: "Keep", style: "cancel" },
        {
          text: "Remove",
          style: "destructive",
          onPress: async () => {
            setGroceryCart(
              groceryRows(await deleteGroceryCartItem(token, row.id)),
            );
            Alert.alert("Item removed", row.product.name, [
              { text: "Done", style: "cancel" },
              {
                text: "Undo",
                onPress: async () =>
                  setGroceryCart(
                    groceryRows(
                      await addGroceryCartItem(token, row.product.id, false),
                    ),
                  ),
              },
            ]);
          },
        },
      ]);
    }
    try {
      const result = await updateGroceryCartItem(
        token,
        row.id,
        row.quantity + delta,
      );
      setGroceryCart(groceryRows(result));
    } catch (error: any) {
      Alert.alert("Could not update cart", error.message);
    }
  };
  return (
    <ScrollView contentContainerStyle={s.cartHub}>
      <Text style={s.serviceTitle}>Your carts</Text>
      <Text style={s.serviceSubtitle}>
        Each service checks out separately for accurate delivery.
      </Text>
      <View style={s.cartTabs}>
        {(
          [
            ["shop", "🛍️", "Shop"],
            ["food", "🍲", "Food"],
            ["grocery", "🥬", "Grocery"],
          ] as [Service, string, string][]
        ).map(([key, icon, label]) => (
          <Pressable
            key={key}
            style={[s.cartTab, active === key && s.cartTabActive]}
            onPress={() => setActive(key)}
          >
            <Text style={s.cartTabIcon}>{icon}</Text>
            <Text
              style={[s.cartTabLabel, active === key && s.cartTabLabelActive]}
            >
              {label}
            </Text>
            <Text style={s.cartTabCount}>{counts[key]}</Text>
          </Pressable>
        ))}
      </View>
      {active === "shop" && (
        <>
          {!token ? (
            <CartEmpty
              icon="🔐"
              title="Sign in to view shop cart"
              copy="Your marketplace cart syncs securely across devices."
              action="Sign in"
              onAction={onLogin}
            />
          ) : !cart.items.length ? (
            <CartEmpty
              icon="🛍️"
              title="Your shop cart is empty"
              copy="Fashion and marketplace products will appear here."
              action="Browse Shop"
              onAction={() => onBrowse("shop")}
            />
          ) : (
            cart.items.map((item) => (
              <View key={item.id} style={s.hubRow}>
                {item.product.image_url ? (
                  <Image
                    source={{ uri: item.product.image_url }}
                    style={s.hubImage}
                  />
                ) : (
                  <View style={s.hubImage} />
                )}
                <View style={s.listGrow}>
                  <Text style={s.cartName}>{item.product.name}</Text>
                  <Text style={s.cartMeta}>
                    {item.variant?.color.name} · {item.variant?.size}
                  </Text>
                  <Text style={s.price}>{money(item.total)}</Text>
                  <View style={s.qty}>
                    <Pressable
                      onPress={async () => {
                        if (item.quantity <= 1)
                          return Alert.alert(
                            "Remove item?",
                            item.product.name,
                            [
                              { text: "Keep", style: "cancel" },
                              {
                                text: "Remove",
                                style: "destructive",
                                onPress: async () => {
                                  await deleteCartItem(token, item.id);
                                  onShopChanged(await getCart(token));
                                  Alert.alert(
                                    "Item removed",
                                    item.product.name,
                                    [
                                      { text: "Done", style: "cancel" },
                                      {
                                        text: "Undo",
                                        onPress: async () => {
                                          if (item.variant) {
                                            await addCartItem(
                                              token,
                                              item.variant.id,
                                              item.quantity,
                                            );
                                            onShopChanged(await getCart(token));
                                          }
                                        },
                                      },
                                    ],
                                  );
                                },
                              },
                            ],
                          );
                        await updateCartItem(token, item.id, item.quantity - 1);
                        onShopChanged(await getCart(token));
                      }}
                    >
                      <Text style={s.qtyBtn}>−</Text>
                    </Pressable>
                    <Text style={s.qtyValue}>{item.quantity}</Text>
                    <Pressable
                      onPress={async () => {
                        await updateCartItem(token, item.id, item.quantity + 1);
                        onShopChanged(await getCart(token));
                      }}
                    >
                      <Text style={s.qtyBtn}>＋</Text>
                    </Pressable>
                  </View>
                  <Pressable
                    onPress={async () => {
                      try {
                        await addWishlist(token, item.product.id);
                        await deleteCartItem(token, item.id);
                        onShopChanged(await getCart(token));
                        Alert.alert("Moved to wishlist", item.product.name);
                      } catch (error: any) {
                        Alert.alert("Could not move item", error.message);
                      }
                    }}
                  >
                    <Text style={s.defaultLink}>Move to wishlist</Text>
                  </Pressable>
                </View>
              </View>
            ))
          )}
        </>
      )}
      {active === "food" && (
        <>
          {!foodCart.length ? (
            <CartEmpty
              icon="🍲"
              title="Your food cart is empty"
              copy="Meals added from a restaurant will appear here."
              action="Browse Food"
              onAction={() => onBrowse("food")}
            />
          ) : (
            foodCart.map((row) => (
              <View key={row.option_id} style={s.hubRow}>
                {row.item.image_url ? (
                  <Image
                    source={{ uri: row.item.image_url }}
                    style={s.hubImage}
                  />
                ) : (
                  <View style={s.hubImage} />
                )}
                <View style={s.listGrow}>
                  <Text style={s.cartName}>{row.item.name}</Text>
                  <Text style={s.cartMeta}>
                    {row.option_name} · Restaurant order
                  </Text>
                  <Text style={s.price}>
                    {money(
                      row.item.options.find((o) => o.id === row.option_id)
                        ?.price || "0",
                    )}
                  </Text>
                  <View style={s.qty}>
                    <Pressable onPress={() => updateFood(row.option_id, -1)}>
                      <Text style={s.qtyBtn}>−</Text>
                    </Pressable>
                    <Text style={s.qtyValue}>{row.quantity}</Text>
                    <Pressable onPress={() => updateFood(row.option_id, 1)}>
                      <Text style={s.qtyBtn}>＋</Text>
                    </Pressable>
                  </View>
                </View>
              </View>
            ))
          )}
        </>
      )}
      {active === "grocery" && (
        <>
          {!groceryCart.length ? (
            <CartEmpty
              icon="🥬"
              title="Your grocery cart is empty"
              copy="Daily essentials added from a local store will appear here."
              action="Browse Groceries"
              onAction={() => onBrowse("grocery")}
            />
          ) : (
            groceryCart.map((row) => (
              <View key={row.product.id} style={s.hubRow}>
                {row.product.image_url ? (
                  <Image
                    source={{ uri: row.product.image_url }}
                    style={s.hubImage}
                  />
                ) : (
                  <View style={s.hubImage} />
                )}
                <View style={s.listGrow}>
                  <Text style={s.cartName}>{row.product.name}</Text>
                  <Text style={s.cartMeta}>
                    {row.product.store_name} · {row.product.unit}
                  </Text>
                  <Text style={s.price}>{money(row.product.price)}</Text>
                  <View style={s.qty}>
                    <Pressable
                      onPress={() => updateGrocery(row.product.id, -1)}
                    >
                      <Text style={s.qtyBtn}>−</Text>
                    </Pressable>
                    <Text style={s.qtyValue}>{row.quantity}</Text>
                    <Pressable onPress={() => updateGrocery(row.product.id, 1)}>
                      <Text style={s.qtyBtn}>＋</Text>
                    </Pressable>
                  </View>
                </View>
              </View>
            ))
          )}
        </>
      )}
      {counts[active] > 0 && (
        <View style={s.cartSummary}>
          <View style={s.totalRow}>
            <Text style={s.totalLabel}>Subtotal</Text>
            <Text style={s.totalValue}>{money(String(totals[active]))}</Text>
          </View>
          <Text style={s.secureNote}>
            {active === "food"
              ? "One restaurant per order"
              : active === "grocery"
                ? "One grocery store per order"
                : "Stock verified securely at checkout"}
          </Text>
          <Pressable
            onPress={() =>
              Alert.alert(
                `Clear ${active} cart?`,
                "All items in this cart will be removed.",
                [
                  { text: "Keep items", style: "cancel" },
                  {
                    text: "Clear",
                    style: "destructive",
                    onPress: async () => {
                      if (active === "shop") {
                        await clearShopCart(token!);
                        onShopChanged(await getCart(token!));
                      }
                      if (active === "food") {
                        await clearFoodCart(token!);
                        setFoodCart([]);
                      }
                      if (active === "grocery") {
                        await clearGroceryCart(token!);
                        setGroceryCart([]);
                      }
                    },
                  },
                ],
              )
            }
          >
            <Text style={s.removeText}>Clear this cart</Text>
          </Pressable>
          <Pressable
            style={s.primary}
            onPress={() => (token ? setCheckout(true) : onLogin())}
          >
            <Text style={s.primaryText}>
              Continue to{" "}
              {active === "food"
                ? "food "
                : active === "grocery"
                  ? "grocery "
                  : ""}
              checkout
            </Text>
          </Pressable>
        </View>
      )}
      <CheckoutModal
        visible={checkout}
        token={token}
        kind={active}
        items={checkoutItems}
        onClose={() => setCheckout(false)}
        onPlace={place}
        onSuccess={completed}
      />
    </ScrollView>
  );
}

function CartEmpty({
  icon,
  title,
  copy,
  action,
  onAction,
}: {
  icon: string;
  title: string;
  copy: string;
  action: string;
  onAction: () => void;
}) {
  return (
    <View style={s.cartEmpty}>
      <Text style={s.emptyIcon}>{icon}</Text>
      <Text style={s.pageTitle}>{title}</Text>
      <Text style={s.emptyCopy}>{copy}</Text>
      <Pressable style={s.outline} onPress={onAction}>
        <Text style={s.outlineText}>{action}</Text>
      </Pressable>
    </View>
  );
}

function CartScreen({
  cart,
  token,
  onLogin,
  onChanged,
  onShop,
}: {
  cart: Cart;
  token: string | null;
  onLogin: () => void;
  onChanged: (cart: Cart) => void;
  onShop: () => void;
}) {
  const [checkoutVisible, setCheckoutVisible] = useState(false);
  if (!token)
    return (
      <ScrollView contentContainerStyle={s.emptyPage}>
        <Text style={s.emptyIcon}>🔐</Text>
        <Text style={s.pageTitle}>Sign in to use your bag</Text>
        <Text style={s.emptyCopy}>
          Your items will stay synced across devices.
        </Text>
        <Pressable style={s.primary} onPress={onLogin}>
          <Text style={s.primaryText}>Sign in</Text>
        </Pressable>
      </ScrollView>
    );
  if (!cart.items.length)
    return (
      <ScrollView contentContainerStyle={s.emptyPage}>
        <Text style={s.emptyIcon}>🛍️</Text>
        <Text style={s.pageTitle}>Your bag is waiting</Text>
        <Text style={s.emptyCopy}>
          Add something you love and it will appear here.
        </Text>
        <Pressable style={s.primary} onPress={onShop}>
          <Text style={s.primaryText}>Continue shopping</Text>
        </Pressable>
      </ScrollView>
    );
  const refresh = async () => onChanged(await getCart(token));
  return (
    <ScrollView contentContainerStyle={s.cartPage}>
      <Text style={s.pageTitle}>Your bag</Text>
      {cart.items.map((item) => (
        <View key={item.id} style={s.cartRow}>
          {item.product.image_url ? (
            <Image
              source={{ uri: item.product.image_url }}
              style={s.cartImage}
            />
          ) : (
            <View style={s.cartImage} />
          )}
          <View style={s.cartInfo}>
            <Text style={s.cartName} numberOfLines={2}>
              {item.product.name}
            </Text>
            <Text style={s.cartMeta}>
              {item.variant?.color.name} · {item.variant?.size}
            </Text>
            <Text style={s.price}>{money(item.total)}</Text>
            <View style={s.qty}>
              <Pressable
                onPress={async () => {
                  item.quantity <= 1
                    ? await deleteCartItem(token, item.id)
                    : await updateCartItem(token, item.id, item.quantity - 1);
                  await refresh();
                }}
              >
                <Text style={s.qtyBtn}>−</Text>
              </Pressable>
              <Text style={s.qtyValue}>{item.quantity}</Text>
              <Pressable
                onPress={async () => {
                  await updateCartItem(token, item.id, item.quantity + 1);
                  await refresh();
                }}
              >
                <Text style={s.qtyBtn}>＋</Text>
              </Pressable>
            </View>
          </View>
        </View>
      ))}
      <View style={s.totalRow}>
        <Text style={s.totalLabel}>Subtotal</Text>
        <Text style={s.totalValue}>{money(cart.subtotal)}</Text>
      </View>
      <Text style={s.secureNote}>
        ✓ Secure order · Stock verified at checkout
      </Text>
      <Pressable style={s.primary} onPress={() => setCheckoutVisible(true)}>
        <Text style={s.primaryText}>Continue to checkout</Text>
      </Pressable>
      <CheckoutModal
        visible={checkoutVisible}
        token={token}
        kind="shop"
        items={cart.items.map((row) => ({
          name: row.product.name,
          meta: `${row.variant?.color.name} · ${row.variant?.size}`,
          image_url: row.product.image_url,
          price: String(Number(row.total) / row.quantity),
          quantity: row.quantity,
        }))}
        onClose={() => setCheckoutVisible(false)}
        onPlace={async (address, _preferences, quoteId, idempotencyKey) =>
          checkoutShop(token, address, quoteId, idempotencyKey, _preferences?.payment_method)
        }
        onSuccess={async () => onChanged(await getCart(token))}
      />
    </ScrollView>
  );
}

function CheckoutModal({
  visible,
  token,
  kind,
  items,
  onClose,
  onPlace,
  onSuccess,
}: {
  visible: boolean;
  token: string | null;
  kind: Service;
  items: {
    name: string;
    meta: string;
    image_url: string | null;
    price: string;
    quantity: number;
  }[];
  onClose: () => void;
  onPlace: (
    addressId: number,
    preferences: any,
    quoteId: string,
    idempotencyKey: string,
  ) => Promise<any>;
  onSuccess: () => void;
}) {
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [addingAddress, setAddingAddress] = useState(false);
  const [addressForm, setAddressForm] = useState({
    full_name: "",
    phone: "",
    address_line_1: "",
    address_line_2: "",
    city: "",
    state: "Uttar Pradesh",
    pincode: "",
    address_type: "Home",
  });
  const [includeCutlery, setIncludeCutlery] = useState(false);
  const [deliveryNote, setDeliveryNote] = useState("");
  const [substitution, setSubstitution] = useState<"contact" | "refund">(
    "contact",
  );
  const [quote, setQuote] = useState<CheckoutQuote | null>(null);
  const [deliveryFix, setDeliveryFix] = useState<{ addressId: number; location: NonNullable<Parameters<typeof getCheckoutQuote>[3]> } | null>(null);
  const [locating, setLocating] = useState(false);
  const quoteRequest = useRef(0);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteError, setQuoteError] = useState("");
  const [submissionKey, setSubmissionKey] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<"cod" | "online">("online");
  const [success, setSuccess] = useState<any>(null);
  useEffect(() => {
    if (visible && token)
      getAddresses(token)
        .then((rows) => {
          setAddresses(rows);
          setSelected(
            rows.find((a) => a.is_default)?.id || rows[0]?.id || null,
          );
        })
        .catch(() => {});
  }, [visible, token]);
  useEffect(() => {
    if (!visible) return;
    setSubmissionKey(`${Date.now()}-${Math.random().toString(36).slice(2)}`);
    setSuccess(null);
    setConfirming(false);
    setDeliveryFix(null);
  }, [visible]);
  const refreshQuote = async () => {
    const requestId = ++quoteRequest.current;
    if (!visible || !token || !selected) { setQuote(null); return; }
    setQuoteLoading(true);
    setQuoteError("");
    setQuote(null);
    try {
      const next = await getCheckoutQuote(token, kind, selected, deliveryFix?.addressId === selected ? deliveryFix.location : undefined);
      if (quoteRequest.current === requestId) setQuote(next);
    } catch (error: any) {
      if (quoteRequest.current === requestId) setQuoteError(error.message);
    } finally {
      if (quoteRequest.current === requestId) setQuoteLoading(false);
    }
  };
  useEffect(() => {
    refreshQuote();
    return () => { quoteRequest.current += 1; };
  }, [visible, token, selected, kind, items.length, deliveryFix]);
  const captureDeliveryLocation = async () => {
    if (!selected) return;
    const addressId = selected;
    setLocating(true);
    try {
      const Location = await import("expo-location");
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) throw new Error("Allow location access to confirm the delivery point.");
      const fix = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      if (fix.coords.accuracy == null || fix.coords.accuracy > 500 || Math.abs(Date.now() - fix.timestamp) > 300000) {
        throw new Error("Move outdoors and capture a more accurate delivery location.");
      }
      setDeliveryFix({ addressId, location: {
        latitude: fix.coords.latitude.toFixed(6), longitude: fix.coords.longitude.toFixed(6),
        gps_accuracy_meters: Math.ceil(fix.coords.accuracy), gps_captured_at: new Date(fix.timestamp).toISOString(),
      } });
    } catch (error: any) { Alert.alert("Delivery location", error.message); }
    finally { setLocating(false); }
  };
  const saveCheckoutAddress = async () => {
    if (!token) return;
    setBusy(true);
    try {
      const address = await addAddress(token, addressForm as any);
      const rows = await getAddresses(token);
      setAddresses(rows);
      setSelected(address.id);
      setAddingAddress(false);
    } catch (error: any) {
      const details = error.details;
      const message =
        details && typeof details === "object"
          ? String(Object.values(details).flat()[0])
          : error.message;
      Alert.alert("Check address details", message);
    } finally {
      setBusy(false);
    }
  };
  const place = async () => {
    if (!selected)
      return Alert.alert(
        "Delivery address required",
        "Add an address from Account, then return to checkout.",
      );
    if (!quote)
      return Alert.alert(
        "Checkout needs refreshing",
        quoteError || "Wait for the latest delivery and total check.",
      );
    setBusy(true);
    try {
      const order = await onPlace(selected, {
        payment_method: paymentMethod,
        include_cutlery: includeCutlery,
        delivery_note: deliveryNote,
        substitution_preference: substitution,
      }, quote.quote_id, submissionKey);
      await onSuccess();
      const result = order.payment_method === "online" ? await payOrder(token!, order) : order;
      setSuccess(result);
      setConfirming(false);
    } catch (error: any) {
      if (error.details?.quote_expired || error.details?.requote_required) {
        setSubmissionKey(`${Date.now()}-${Math.random().toString(36).slice(2)}`);
        await refreshQuote();
      }
      Alert.alert("Could not place order", error.message);
    } finally {
      setBusy(false);
    }
  };
  if (success) {
    return (
      <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
        <SafeAreaView style={s.authPage} edges={["top", "bottom"]}>
          <ScrollView contentContainerStyle={s.modalContent}>
            <View style={s.successBadge}><Text style={s.successBadgeText}>✓</Text></View>
            <Text style={s.successTitle}>Order confirmed</Text>
            <Text style={s.successCopy}>
              Your order #{success.id} is safely placed. Payment: {success.payment_status}.
            </Text>
            <View style={s.checkoutAddressForm}>
              <View style={s.totalRow}><Text style={s.totalLabel}>Amount due</Text><Text style={s.totalValue}>{money(success.total)}</Text></View>
              <Text style={s.secureNote}>Delivery: {quote?.price.eta || "Updates will appear in My orders"}</Text>
              <Text style={s.secureNote}>Delivering to {quote?.price.address.label}</Text>
            </View>
            <Pressable style={s.primary} onPress={onClose}><Text style={s.primaryText}>Continue shopping</Text></Pressable>
          </ScrollView>
        </SafeAreaView>
      </Modal>
    );
  }
  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={s.authPage} edges={["top", "bottom"]}>
        <View style={s.modalHeader}>
          <View>
            <Text style={s.modalTitle}>Checkout</Text>
            <Text style={s.checkoutStep}>REVIEW · ADDRESS · PAYMENT</Text>
          </View>
          <Pressable onPress={onClose}>
            <Text style={s.close}>×</Text>
          </Pressable>
        </View>
        <ScrollView
          contentContainerStyle={s.modalContent}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={s.sectionTitle}>Order summary</Text>
          {items.map((row, index) => (
            <View key={`${row.name}-${index}`} style={s.checkoutItem}>
              {row.image_url ? (
                <Image source={{ uri: row.image_url }} style={s.miniImage} />
              ) : (
                <View style={s.miniImage} />
              )}
              <View style={s.listGrow}>
                <Text style={s.listTitle}>{row.name}</Text>
                <Text style={s.listMeta}>
                  {row.meta} · Qty {row.quantity}
                </Text>
              </View>
              <Text style={s.listPrice}>
                {money(String(Number(row.price) * row.quantity))}
              </Text>
            </View>
          ))}
          <Text style={s.sectionTitle}>Deliver to</Text>
          {addresses.map((address) => (
            <Pressable
              key={address.id}
              style={[
                s.addressChoice,
                selected === address.id && s.addressSelected,
              ]}
              onPress={() => setSelected(address.id)}
            >
              <View style={s.radio}>
                {selected === address.id && <View style={s.radioDot} />}
              </View>
              <View style={s.listGrow}>
                <Text style={s.listTitle}>
                  {address.full_name} · {address.address_type}
                </Text>
                <Text style={s.addressText}>
                  {address.address_line_1}, {address.city} {address.pincode}
                </Text>
              </View>
            </Pressable>
          ))}
          {selected && (
            <View style={s.checkoutAddressForm}>
              <Text style={s.listTitle}>Delivery point for local riders</Text>
              <Text style={s.addressText}>Capture only while you are at the selected delivery address. Local delivery requires this location.</Text>
              <Pressable style={[s.outline, locating && s.disabled]} disabled={locating || busy} onPress={captureDeliveryLocation}>
                <Text style={s.viewDetails}>{locating ? "Capturing location…" : deliveryFix?.addressId === selected ? "Recapture delivery location" : "Use my current location for this address"}</Text>
              </Pressable>
              {deliveryFix?.addressId === selected && <Text style={s.secureNote}>Delivery point captured for this address.</Text>}
            </View>
          )}
          {addingAddress ? (
            <View style={s.checkoutAddressForm}>
              <Field
                label="Full name"
                value={addressForm.full_name}
                onChange={(v) =>
                  setAddressForm({ ...addressForm, full_name: v })
                }
              />
              <Field
                label="Mobile number"
                value={addressForm.phone}
                onChange={(v) => setAddressForm({ ...addressForm, phone: v })}
                keyboard="phone-pad"
              />
              <Field
                label="House, street and area"
                value={addressForm.address_line_1}
                onChange={(v) =>
                  setAddressForm({ ...addressForm, address_line_1: v })
                }
              />
              <Field
                label="Landmark (optional)"
                value={addressForm.address_line_2}
                onChange={(v) =>
                  setAddressForm({ ...addressForm, address_line_2: v })
                }
              />
              <Field
                label="City"
                value={addressForm.city}
                onChange={(v) => setAddressForm({ ...addressForm, city: v })}
              />
              <Field
                label="State"
                value={addressForm.state}
                onChange={(v) => setAddressForm({ ...addressForm, state: v })}
              />
              <Field
                label="Pincode"
                value={addressForm.pincode}
                onChange={(v) => setAddressForm({ ...addressForm, pincode: v })}
                keyboard="number-pad"
              />
              <Pressable
                disabled={busy}
                style={[s.primary, busy && s.disabled]}
                onPress={saveCheckoutAddress}
              >
                <Text style={s.primaryText}>Save and deliver here</Text>
              </Pressable>
            </View>
          ) : (
            <Pressable
              style={s.addAddressButton}
              onPress={() => setAddingAddress(true)}
            >
              <Text style={s.addAddressText}>＋ Add a new address</Text>
            </Pressable>
          )}
          {kind === "food" && (
            <>
              <Text style={s.sectionTitle}>Delivery preferences</Text>
              <Pressable
                style={s.paymentChoice}
                onPress={() => setIncludeCutlery(!includeCutlery)}
              >
                <Text style={s.paymentIcon}>{includeCutlery ? "✓" : "○"}</Text>
                <View>
                  <Text style={s.listTitle}>Include disposable cutlery</Text>
                  <Text style={s.listMeta}>Choose only when needed</Text>
                </View>
              </Pressable>
              <TextInput
                value={deliveryNote}
                onChangeText={(value) => setDeliveryNote(value.slice(0, 300))}
                placeholder="Delivery instructions (optional)"
                style={s.locationInput}
              />
            </>
          )}
          {kind === "grocery" && (
            <>
              <Text style={s.sectionTitle}>Unavailable item preference</Text>
              {(["contact", "refund"] as const).map((value) => (
                <Pressable
                  key={value}
                  style={[
                    s.paymentChoice,
                    substitution !== value && s.unselectedChoice,
                  ]}
                  onPress={() => setSubstitution(value)}
                >
                  <Text style={s.paymentIcon}>
                    {substitution === value ? "✓" : "○"}
                  </Text>
                  <View>
                    <Text style={s.listTitle}>
                      {value === "contact"
                        ? "Contact me for substitutes"
                        : "Refund unavailable items"}
                    </Text>
                  </View>
                </Pressable>
              ))}
            </>
          )}
          <Text style={s.sectionTitle}>Payment</Text>
          {(["online", "cod"] as const).map(method => <Pressable key={method} accessibilityRole="radio" accessibilityState={{ checked: paymentMethod === method, disabled: method === "cod" && !quote?.price.cod_eligible }} disabled={busy || (method === "cod" && !quote?.price.cod_eligible)} style={s.paymentChoice} onPress={() => setPaymentMethod(method)}><Text style={s.paymentIcon}>{paymentMethod === method ? "●" : "○"}</Text><Text style={s.listTitle}>{method === "online" ? "Pay online · UPI, cards, netbanking" : "Cash on delivery"}</Text></Pressable>)}
          {quote && !quote.price.cod_eligible && <Text style={s.errorText}>{quote.price.cod_unavailable_reason}</Text>}
          <Text style={s.sectionTitle}>Price details</Text>
          {quoteLoading ? (
            <View style={s.loadingRow}>
              <ActivityIndicator color={C.orange} />
              <Text style={s.listMeta}>Checking stock, delivery and latest prices…</Text>
            </View>
          ) : quoteError ? (
            <View style={s.quoteError}>
              <Text style={s.errorText}>{quoteError}</Text>
              <Pressable onPress={refreshQuote}><Text style={s.link}>Try again</Text></Pressable>
            </View>
          ) : quote ? (
            <View style={s.checkoutAddressForm}>
              <View style={s.totalRow}><Text style={s.totalLabel}>Items subtotal</Text><Text style={s.listPrice}>{money(quote.price.item_subtotal)}</Text></View>
              <View style={s.totalRow}><Text style={s.totalLabel}>Delivery</Text><Text style={s.listPrice}>{Number(quote.price.delivery_charge) ? money(quote.price.delivery_charge) : "FREE"}</Text></View>
              {Number(quote.price.discount) > 0 && <View style={s.totalRow}><Text style={s.totalLabel}>Discount</Text><Text style={s.discountText}>− {money(quote.price.discount)}</Text></View>}
              <View style={s.totalRow}><Text style={s.totalLabel}>Total</Text><Text style={s.totalValue}>{money(quote.price.total)}</Text></View>
              <Text style={s.secureNote}>Prices include applicable taxes · {quote.price.eta} · Fulfilled by {quote.price.source}</Text>
            </View>
          ) : null}
          {confirming && quote && (
            <View style={s.confirmBox}>
              <Text style={s.listTitle}>Confirm order</Text>
              <Text style={s.addressText}>{paymentMethod === "cod" ? "Pay on delivery" : "Pay securely with Razorpay"}: {money(quote.price.total)}. Deliver to {quote.price.address.label}.</Text>
              <Pressable disabled={busy} style={[s.primary, busy && s.disabled]} onPress={place}>
                {busy ? <ActivityIndicator color="#fff" /> : <Text style={s.primaryText}>Confirm and place order</Text>}
              </Pressable>
              <Pressable disabled={busy} onPress={() => setConfirming(false)}><Text style={s.centerLink}>Go back</Text></Pressable>
            </View>
          )}
          <Pressable
            disabled={busy || !selected || quoteLoading || !quote || (paymentMethod === "cod" && !quote.price.cod_eligible) || confirming}
            style={[s.primary, (busy || !selected || quoteLoading || !quote || (paymentMethod === "cod" && !quote?.price.cod_eligible) || confirming) && s.disabled]}
            onPress={() => setConfirming(true)}
          >
            <Text style={s.primaryText}>{quote ? `Review order · ${money(quote.price.total)}` : "Review order"}</Text>
          </Pressable>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function AccountSectionModal({
  view,
  token,
  onClose,
  onOpenProduct,
}: {
  view: "profile" | "orders" | "addresses" | "wishlist" | null;
  token: string;
  onClose: () => void;
  onOpenProduct: (product: Product) => void;
}) {
  const [loading, setLoading] = useState(true);
  const [orders, setOrders] = useState<Order[]>([]);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [wishlist, setWishlist] = useState<Product[]>([]);
  const [adding, setAdding] = useState(false);
  const [editingAddressId, setEditingAddressId] = useState<number | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [profile, setProfile] = useState({
    first_name: "",
    last_name: "",
    phone: "",
  });
  const [form, setForm] = useState({
    full_name: "",
    phone: "",
    address_line_1: "",
    address_line_2: "",
    city: "",
    state: "Uttar Pradesh",
    pincode: "",
    address_type: "Home",
  });
  const reload = async () => {
    if (!view) return;
    setLoading(true);
    try {
      if (view === "profile") {
        const row = await getProfile(token);
        setProfile({
          first_name: row.first_name || "",
          last_name: row.last_name || "",
          phone: row.phone || "",
        });
      }
      if (view === "orders") setOrders(await getOrders(token));
      if (view === "addresses") setAddresses(await getAddresses(token));
      if (view === "wishlist") setWishlist(await getWishlist(token));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    reload();
  }, [view]);
  if (!view) return null;
  const title =
    view === "profile"
      ? "Personal details"
      : view === "orders"
        ? "My orders"
        : view === "addresses"
          ? "Saved addresses"
          : "Wishlist";
  const saveAddress = async () => {
    try {
      if (editingAddressId)
        await updateAddress(token, editingAddressId, form as any);
      else await addAddress(token, form as any);
      setAdding(false);
      setEditingAddressId(null);
      setForm({
        full_name: "",
        phone: "",
        address_line_1: "",
        address_line_2: "",
        city: "",
        state: "Uttar Pradesh",
        pincode: "",
        address_type: "Home",
      });
      await reload();
    } catch (error: any) {
      Alert.alert("Could not save address", error.message);
    }
  };
  return (
    <Modal
      visible
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={s.authPage} edges={["top", "bottom"]}>
        <View style={s.modalHeader}>
          <Text style={s.modalTitle}>{title}</Text>
          <Pressable onPress={onClose}>
            <Text style={s.close}>×</Text>
          </Pressable>
        </View>
        {loading ? (
          <ActivityIndicator color={C.green} size="large" style={s.loader} />
        ) : (
          <ScrollView contentContainerStyle={s.modalContent}>
            {view === "profile" && (
              <>
                <Text style={s.secureNote}>
                  Complete these details so checkout forms and customer support
                  can identify you correctly.
                </Text>
                <Field
                  label="First name"
                  value={profile.first_name}
                  onChange={(value) =>
                    setProfile({ ...profile, first_name: value })
                  }
                />
                <Field
                  label="Last name"
                  value={profile.last_name}
                  onChange={(value) =>
                    setProfile({ ...profile, last_name: value })
                  }
                />
                <Field
                  label="Mobile number"
                  value={profile.phone}
                  onChange={(value) => setProfile({ ...profile, phone: value })}
                  keyboard="phone-pad"
                />
                <Pressable
                  style={s.primary}
                  onPress={async () => {
                    try {
                      await updateProfile(token, profile);
                      Alert.alert(
                        "Profile saved",
                        "Your account details are now updated.",
                      );
                      onClose();
                    } catch (error: any) {
                      Alert.alert("Could not save profile", error.message);
                    }
                  }}
                >
                  <Text style={s.primaryText}>Save personal details</Text>
                </Pressable>
              </>
            )}
            {view === "orders" && (
              <>
                {orders.map((order) => (
                  <Pressable
                    key={`${order.kind}-${order.id}`}
                    style={s.listCard}
                    onPress={() => setSelectedOrder(order)}
                  >
                    <View style={s.listRow}>
                      <Text style={s.listTitle}>
                        {order.kind === "food"
                          ? "Food"
                          : order.kind === "grocery"
                            ? "Grocery"
                            : "Shop"}{" "}
                        order #{order.id}
                      </Text>
                      <Text style={s.statusPill}>
                        {order.status.replaceAll("_", " ")}
                      </Text>
                    </View>
                    <Text style={s.listMeta}>
                      {new Date(order.created_at).toLocaleDateString("en-IN")} ·{" "}
                      {order.items.length} item(s) · COD
                    </Text>
                    <View style={s.listRow}>
                      <Text style={s.listPrice}>
                        {money(order.total_price)}
                      </Text>
                      <Text style={s.viewDetails}>Track & manage →</Text>
                    </View>
                  </Pressable>
                ))}
                {!orders.length && (
                  <EmptyState
                    icon="📦"
                    title="No orders yet"
                    copy="Shop, food and grocery orders from this account will appear together here."
                  />
                )}
                <OrderDetailModal
                  order={selectedOrder}
                  token={token}
                  onClose={() => setSelectedOrder(null)}
                  onChanged={async () => {
                    setSelectedOrder(null);
                    await reload();
                  }}
                />
              </>
            )}
            {view === "wishlist" && (
              <>
                {wishlist.map((product) => (
                  <Pressable
                    key={product.id}
                    style={s.listCard}
                    onPress={() => onOpenProduct(product)}
                  >
                    <View style={s.listRow}>
                      {product.image_url && (
                        <Image
                          source={{ uri: product.image_url }}
                          style={s.miniImage}
                        />
                      )}
                      <View style={s.listGrow}>
                        <Text style={s.listTitle}>{product.name}</Text>
                        <Text style={s.listPrice}>{money(product.price)}</Text>
                      </View>
                      <Pressable
                        onPress={async (event) => {
                          event.stopPropagation();
                          await removeWishlist(token, product.id);
                          await reload();
                        }}
                      >
                        <Text style={s.removeText}>Remove</Text>
                      </Pressable>
                    </View>
                    <Pressable
                      style={s.addButton}
                      onPress={async (event) => {
                        event.stopPropagation();
                        try {
                          const detail = await getProduct(product.slug, token);
                          const variant = detail.variants?.find(
                            (row) => row.stock > 0,
                          );
                          if (!variant)
                            return Alert.alert(
                              "Unavailable",
                              "No variant is currently in stock.",
                            );
                          await addCartItem(token, variant.id);
                          Alert.alert("Added to cart", product.name);
                        } catch (error: any) {
                          Alert.alert("Could not add", error.message);
                        }
                      }}
                    >
                      <Text style={s.addText}>Add to Shop cart</Text>
                    </Pressable>
                  </Pressable>
                ))}
                {!wishlist.length && (
                  <EmptyState
                    icon="♡"
                    title="Your wishlist is empty"
                    copy="Tap the heart on a product to save it here."
                  />
                )}
              </>
            )}
            {view === "addresses" && (
              <>
                {addresses.map((address) => (
                  <View key={address.id} style={s.listCard}>
                    <View style={s.listRow}>
                      <Text style={s.listTitle}>
                        {address.address_type}
                        {address.is_default ? " · Default" : ""}
                      </Text>
                      <Pressable
                        onPress={() =>
                          Alert.alert(
                            "Delete address?",
                            "This saved address will be removed.",
                            [
                              { text: "Keep", style: "cancel" },
                              {
                                text: "Delete",
                                style: "destructive",
                                onPress: async () => {
                                  await deleteAddress(token, address.id);
                                  await reload();
                                },
                              },
                            ],
                          )
                        }
                      >
                        <Text style={s.removeText}>Delete</Text>
                      </Pressable>
                    </View>
                    <Text style={s.listMeta}>
                      {address.full_name} · {address.phone}
                    </Text>
                    <Text style={s.addressText}>
                      {address.address_line_1}
                      {address.address_line_2
                        ? `, ${address.address_line_2}`
                        : ""}
                      , {address.city}, {address.state} {address.pincode}
                    </Text>
                    <Pressable
                      onPress={() => {
                        setForm({
                          full_name: address.full_name,
                          phone: address.phone,
                          address_line_1: address.address_line_1,
                          address_line_2: address.address_line_2,
                          city: address.city,
                          state: address.state,
                          pincode: address.pincode,
                          address_type: address.address_type,
                        });
                        setEditingAddressId(address.id);
                        setAdding(true);
                      }}
                    >
                      <Text style={s.defaultLink}>Edit address</Text>
                    </Pressable>
                    {!address.is_default && (
                      <Pressable
                        onPress={async () => {
                          await setDefaultAddress(token, address.id);
                          await reload();
                        }}
                      >
                        <Text style={s.defaultLink}>Make default</Text>
                      </Pressable>
                    )}
                  </View>
                ))}
                {adding ? (
                  <View style={s.addressForm}>
                    <Field
                      label="Full name"
                      value={form.full_name}
                      onChange={(v) => setForm({ ...form, full_name: v })}
                    />
                    <Field
                      label="Phone"
                      value={form.phone}
                      onChange={(v) => setForm({ ...form, phone: v })}
                      keyboard="phone-pad"
                    />
                    <Field
                      label="House, street and area"
                      value={form.address_line_1}
                      onChange={(v) => setForm({ ...form, address_line_1: v })}
                    />
                    <Field
                      label="Landmark (optional)"
                      value={form.address_line_2}
                      onChange={(v) => setForm({ ...form, address_line_2: v })}
                    />
                    <Field
                      label="City"
                      value={form.city}
                      onChange={(v) => setForm({ ...form, city: v })}
                    />
                    <Field
                      label="State"
                      value={form.state}
                      onChange={(v) => setForm({ ...form, state: v })}
                    />
                    <Field
                      label="Pincode"
                      value={form.pincode}
                      onChange={(v) => setForm({ ...form, pincode: v })}
                      keyboard="number-pad"
                    />
                    <Pressable style={s.primary} onPress={saveAddress}>
                      <Text style={s.primaryText}>
                        {editingAddressId ? "Update address" : "Save address"}
                      </Text>
                    </Pressable>
                  </View>
                ) : (
                  <Pressable style={s.primary} onPress={() => setAdding(true)}>
                    <Text style={s.primaryText}>Add new address</Text>
                  </Pressable>
                )}
              </>
            )}
          </ScrollView>
        )}
      </SafeAreaView>
    </Modal>
  );
}

function OrderDetailModal({
  order,
  token,
  onClose,
  onChanged,
}: {
  order: Order | null;
  token: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [mode, setMode] = useState<"support" | "return" | null>(null);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  if (!order) return null;
  const stages =
    order.kind === "shop"
      ? [
          "Pending",
          "Processing",
          "Packed",
          "Shipped",
          "Out for Delivery",
          "Delivered",
        ]
      : order.kind === "food"
        ? [
            "placed",
            "accepted",
            "preparing",
            "ready",
            "out_for_delivery",
            "delivered",
          ]
        : ["placed", "accepted", "packing", "ready", "shipped", "delivered"];
  const current = Math.max(0, stages.indexOf(order.status));
  const submit = async () => {
    if (!mode) return;
    setBusy(true);
    try {
      await createCareRequest(token, order, mode, reason, message);
      Alert.alert(
        "Request received",
        `Your ${mode} request has been created. Our team will update its status in this order.`,
      );
      onChanged();
    } catch (error: any) {
      Alert.alert("Could not create request", error.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      visible
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={s.authPage} edges={["top", "bottom"]}>
        <View style={s.modalHeader}>
          <View>
            <Text style={s.modalTitle}>
              {order.kind.toUpperCase()} order #{order.id}
            </Text>
            <Text style={s.checkoutStep}>ORDER DETAILS & TRACKING</Text>
          </View>
          <Pressable onPress={onClose}>
            <Text style={s.close}>×</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={s.modalContent}>
          <Text style={s.sectionTitle}>Delivery progress</Text>
          {order.status.toLowerCase() === "cancelled" ? (
            <View style={s.errorBox}>
              <Text style={s.errorText}>This order was cancelled.</Text>
            </View>
          ) : (
            stages.map((stage, index) => (
              <View key={stage} style={s.timelineRow}>
                <View
                  style={[s.timelineDot, index <= current && s.timelineDone]}
                />
                <View>
                  <Text
                    style={[s.listTitle, index > current && s.timelineMuted]}
                  >
                    {stage.replaceAll("_", " ")}
                  </Text>
                  {index === current && (
                    <Text style={s.storeMeta}>Current status</Text>
                  )}
                </View>
              </View>
            ))
          )}
          {!!order.courier && (
            <Text style={s.secureNote}>
              Fulfilment: {order.courier}
              {order.tracking_number
                ? ` · Tracking ${order.tracking_number}`
                : ""}
            </Text>
          )}
          <Text style={s.sectionTitle}>Items</Text>
          {order.items.map((item) => (
            <View key={item.id} style={s.checkoutItem}>
              {item.image_url ? (
                <Image source={{ uri: item.image_url }} style={s.miniImage} />
              ) : (
                <View style={s.miniImage} />
              )}
              <View style={s.listGrow}>
                <Text style={s.listTitle}>{item.product_name}</Text>
                <Text style={s.listMeta}>
                  {item.product_color} {item.product_size} · Qty {item.quantity}
                </Text>
              </View>
              <Text style={s.listPrice}>{money(item.line_total)}</Text>
            </View>
          ))}
          <View style={s.totalRow}>
            <Text style={s.totalLabel}>Order total</Text>
            <Text style={s.totalValue}>{money(order.total_price)}</Text>
          </View>
          <Text style={s.secureNote}>
            {order.payment_method === "cod" ? "Cash on delivery" : "Online payment"} · Payment {order.payment_status}
          </Text>
          {order.payment_method === "online" && order.payment_status !== "Paid" && !["cancelled", "returned"].includes(order.status.toLowerCase()) && <>
            <Pressable accessibilityRole="button" disabled={busy} style={s.primary} onPress={async () => { setBusy(true); try { await payOrder(token, order); onChanged(); } catch (e: any) { Alert.alert("Payment", e.message); } finally { setBusy(false); } }}><Text style={s.primaryText}>Pay pending order</Text></Pressable>
            <Pressable accessibilityRole="button" disabled={busy} style={s.outline} onPress={async () => { setBusy(true); try { const result = await recoverPayment(token, order.kind, order.id); onChanged(); Alert.alert("Payment status", result.payment_status); } catch (e: any) { Alert.alert("Payment", e.message); } finally { setBusy(false); } }}><Text style={s.outlineText}>Check payment status</Text></Pressable>
          </>}
          {order.can_cancel && (
            <Pressable
              style={s.dangerButton}
              onPress={() =>
                Alert.alert(
                  "Cancel this order?",
                  "Stock will be released and this cannot be undone.",
                  [
                    { text: "Keep order", style: "cancel" },
                    {
                      text: "Cancel order",
                      style: "destructive",
                      onPress: async () => {
                        try {
                          await cancelOrder(
                            token,
                            order,
                            "Cancelled by customer in mobile app",
                          );
                          onChanged();
                        } catch (error: any) {
                          Alert.alert("Could not cancel", error.message);
                        }
                      },
                    },
                  ],
                )
              }
            >
              <Text style={s.dangerText}>Cancel order</Text>
            </Pressable>
          )}
          <CustomerOrderTools key={`${order.kind}-${order.id}`} token={token} order={order} />
          <Pressable style={s.outline} onPress={() => setMode("support")}>
            <Text style={s.outlineText}>Get help with this order</Text>
          </Pressable>
          {mode && (
            <View style={s.careForm}>
              <Text style={s.sectionTitle}>
                {mode === "return" ? "Return request" : "Contact support"}
              </Text>
              <Field label="Reason" value={reason} onChange={setReason} />
              <Field
                label="Describe what happened"
                value={message}
                onChange={setMessage}
              />
              <Pressable
                disabled={busy}
                style={[s.primary, busy && s.disabled]}
                onPress={submit}
              >
                {busy ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={s.primaryText}>Submit request</Text>
                )}
              </Pressable>
            </View>
          )}
          {Object.entries(order.care || {}).map(([type, row]) => (
            <View key={type} style={s.stockBanner}>
              <Text style={s.stockBannerText}>
                {type.toUpperCase()} · {row.status}
              </Text>
              <Text style={s.storeMeta}>{row.reason}</Text>
            </View>
          ))}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function EmptyState({
  icon,
  title,
  copy,
}: {
  icon: string;
  title: string;
  copy: string;
}) {
  return (
    <View style={s.emptyService}>
      <Text style={s.emptyIcon}>{icon}</Text>
      <Text style={s.pageTitle}>{title}</Text>
      <Text style={s.emptyCopy}>{copy}</Text>
    </View>
  );
}

export default function App() {
  return (
    <AppErrorBoundary><SafeAreaProvider>
      <ZiyaApp />
    </SafeAreaProvider></AppErrorBoundary>
  );
}

const s: any = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.white },
  body: { flex: 1 },
  heartActive: { color: "#D14343" },
  relatedRow: { paddingHorizontal: 18, gap: 12, paddingBottom: 20 },
  searchToolbar: {
    flexDirection: "row",
    alignItems: "center",
    paddingRight: 18,
  },
  searchGrow: { flex: 1, marginRight: 8 },
  filterButton: {
    backgroundColor: C.ink,
    borderRadius: 14,
    paddingHorizontal: 15,
    paddingVertical: 16,
  },
  filterButtonText: { color: "#fff", fontWeight: "800" },
  filterFields: { flexDirection: "row", gap: 12 },
  filterChips: {
    paddingHorizontal: 18,
    gap: 8,
    paddingBottom: 12,
    flexDirection: "row",
    flexWrap: "wrap",
  },
  filterChip: {
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 18,
    paddingHorizontal: 13,
    paddingVertical: 8,
    backgroundColor: "#fff",
  },
  filterChipActive: { borderColor: C.green, backgroundColor: "#E8F7F1" },
  noteInput: {
    height: 90,
    textAlignVertical: "top",
    paddingTop: 14,
    marginTop: 10,
  },
  specRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: C.line,
  },
  mrp: { color: C.muted, textDecorationLine: "line-through", marginTop: 9 },
  timelineRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    minHeight: 48,
  },
  timelineDot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: C.line,
  },
  timelineDone: { backgroundColor: C.green },
  timelineMuted: { color: C.muted },
  dangerButton: {
    borderWidth: 1,
    borderColor: "#B42318",
    borderRadius: 14,
    paddingVertical: 13,
    alignItems: "center",
    marginTop: 20,
  },
  dangerText: { color: "#B42318", fontWeight: "900" },
  careForm: {
    marginTop: 12,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: C.line,
  },
  page: { paddingBottom: 28 },
  header: {
    height: 68,
    paddingHorizontal: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderBottomColor: C.line,
  },
  locationButton: { width: 128 },
  eyebrow: {
    fontSize: 9,
    letterSpacing: 1.4,
    color: C.muted,
    fontWeight: "700",
  },
  location: { fontSize: 14, fontWeight: "700", color: C.ink, marginTop: 2 },
  logo: {
    width: 46,
    height: 46,
    borderRadius: 14,
    backgroundColor: "#F1FBF6",
    alignItems: "center",
    justifyContent: "center",
  },
  logoImage: { width: 40, height: 40, resizeMode: "contain" },
  headerCart: {
    width: 45,
    height: 45,
    alignItems: "flex-end",
    justifyContent: "center",
  },
  cartIcon: { fontSize: 22 },
  badge: {
    position: "absolute",
    right: -5,
    top: -2,
    backgroundColor: C.green,
    color: "#fff",
    fontSize: 10,
    fontWeight: "800",
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    textAlign: "center",
    lineHeight: 18,
  },
  serviceStrip: {
    height: 70,
    flexDirection: "row",
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 5,
    borderBottomWidth: 1,
    borderBottomColor: C.line,
  },
  serviceButton: {
    flex: 1,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  serviceActive: { backgroundColor: "#E8F7F1" },
  serviceIcon: { fontSize: 21 },
  serviceLabel: {
    fontSize: 10,
    fontWeight: "700",
    color: C.muted,
    marginTop: 2,
  },
  serviceLabelActive: { color: C.green, fontWeight: "900" },
  hero: {
    margin: 16,
    borderRadius: 24,
    minHeight: 205,
    padding: 22,
    overflow: "hidden",
    flexDirection: "row",
    alignItems: "center",
  },
  heroCopy: { flex: 1, zIndex: 2 },
  heroKicker: {
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1.5,
    color: C.green,
  },
  heroTitle: {
    fontSize: 26,
    lineHeight: 32,
    fontWeight: "900",
    color: C.ink,
    marginTop: 8,
  },
  shopButton: {
    marginTop: 18,
    backgroundColor: C.ink,
    alignSelf: "flex-start",
    paddingHorizontal: 17,
    paddingVertical: 11,
    borderRadius: 12,
  },
  shopText: { color: "#fff", fontWeight: "800", fontSize: 13 },
  heroOrb: {
    width: 125,
    height: 125,
    borderRadius: 63,
    backgroundColor: "rgba(15,139,109,.09)",
    alignItems: "center",
    justifyContent: "center",
    marginRight: -45,
  },
  heroBrand: { width: 100, height: 100, resizeMode: "contain" },
  sectionRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 18,
    marginTop: 14,
    marginBottom: 14,
  },
  heading: { fontSize: 20, fontWeight: "900", color: C.ink },
  link: { fontSize: 13, fontWeight: "700", color: C.orange },
  categories: { paddingHorizontal: 14, gap: 10 },
  category: { width: 76, alignItems: "center" },
  categoriesGrid: {
  paddingHorizontal: 14,
  flexDirection: "row",
  flexWrap: "wrap",
  gap: 16,
  paddingBottom: 30,
 },

 categoryGridItem: {
  width: 76,
  alignItems: "center",
  marginBottom: 10,
 },
 categoryIcon: {
    width: 64,
    height: 64,
    borderRadius: 22,
    backgroundColor: C.cream,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  categorySelected: { borderWidth: 2, borderColor: C.orange },
  categoryImage: { width: "100%", height: "100%", resizeMode: "cover" },
  categoryEmoji: { fontSize: 29 },
  categoryLabel: {
    fontSize: 12,
    color: C.ink,
    fontWeight: "600",
    marginTop: 7,
  },
  grid: {
    paddingHorizontal: 14,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
    paddingBottom: 30,
  },
  card: {
    width: "48%",
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 18,
    padding: 9,
    backgroundColor: "#fff",
  },
  imageWrap: {
    height: 145,
    borderRadius: 14,
    backgroundColor: "#F6F4EF",
    overflow: "hidden",
    alignItems: "center",
    justifyContent: "center",
  },
  productImage: { width: "100%", height: "100%", resizeMode: "cover" },
  placeholder: { fontSize: 25, fontWeight: "900", color: "#C7BFB2" },
  heart: {
    position: "absolute",
    right: 8,
    top: 8,
    width: 29,
    height: 29,
    borderRadius: 15,
    backgroundColor: "rgba(255,255,255,.9)",
    alignItems: "center",
    justifyContent: "center",
  },
  productName: {
    fontSize: 13,
    fontWeight: "700",
    color: C.ink,
    lineHeight: 18,
    minHeight: 36,
    marginTop: 9,
  },
  price: { fontSize: 16, fontWeight: "900", color: C.ink, marginTop: 3 },
  viewDetails: {
    color: C.green,
    fontWeight: "900",
    fontSize: 12,
    marginTop: 9,
  },
  addButton: {
    marginTop: 9,
    borderWidth: 1,
    borderColor: C.orange,
    borderRadius: 10,
    paddingVertical: 8,
    alignItems: "center",
  },
  addText: { color: C.dark, fontWeight: "800", fontSize: 12 },
  loader: { marginVertical: 40 },
  errorBox: {
    margin: 18,
    padding: 20,
    borderRadius: 16,
    backgroundColor: "#FFF1ED",
  },
  errorText: { color: "#8A3021", lineHeight: 20 },
  retry: { color: C.dark, fontWeight: "800", marginTop: 10 },
  nav: {
    height: 68,
    borderTopWidth: 1,
    borderTopColor: C.line,
    flexDirection: "row",
    backgroundColor: "#fff",
  },
  navItem: { flex: 1, alignItems: "center", justifyContent: "center" },
  navIcon: { fontSize: 22, color: "#87909D" },
  navLabel: { fontSize: 10, fontWeight: "700", marginTop: 2, color: "#87909D" },
  navActive: { color: C.dark },
  detailPage: { padding: 18, paddingBottom: 38 },
  back: { alignSelf: "flex-start", paddingVertical: 10 },
  backText: { fontWeight: "800", fontSize: 16, color: C.ink },
  detailImageWrap: {
    height: 360,
    borderRadius: 26,
    overflow: "hidden",
    backgroundColor: "#F6F4EF",
    alignItems: "center",
    justifyContent: "center",
  },
  detailImage: { width: "100%", height: "100%", resizeMode: "contain" },
  zoomBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,.94)",
    alignItems: "center",
    justifyContent: "center",
  },
  zoomImage: { width: "100%", height: "78%", resizeMode: "contain" },
  zoomClose: { color: "#fff", marginTop: 20, fontWeight: "800" },
  detailPlaceholder: { fontWeight: "900", fontSize: 25, color: "#B8AFA2" },
  detailTitle: {
    fontSize: 25,
    lineHeight: 32,
    fontWeight: "900",
    color: C.ink,
    marginTop: 20,
  },
  detailPrice: { fontSize: 24, fontWeight: "900", color: C.ink, marginTop: 8 },
  ratingRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 8,
    gap: 8,
  },
  stars: { color: "#F5A623", fontSize: 17 },
  ratingCopy: { color: C.muted, fontSize: 12 },
  inclusive: {
    fontSize: 12,
    lineHeight: 18,
    color: C.green,
    marginTop: 8,
    fontWeight: "700",
  },
  thumbnails: { flexDirection: "row", flexWrap: "wrap", gap: 9, paddingVertical: 12 },
  thumbWrap: {
    width: 62,
    height: 62,
    borderRadius: 11,
    borderWidth: 1,
    borderBottomColor: C.line,
    overflow: "hidden",
  },
  thumbSelected: { borderColor: C.ink, borderWidth: 2 },
  thumb: { width: "100%", height: "100%", resizeMode: "cover" },
  infoGrid: {
    flexDirection: "row",
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: C.line,
    marginTop: 20,
    paddingVertical: 15,
  },
  infoHalf: { flex: 1 },
  infoLabel: {
    fontSize: 11,
    color: C.muted,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  infoValue: { fontSize: 14, color: C.ink, fontWeight: "900", marginTop: 4 },
  stockBanner: {
    backgroundColor: "#E8F7F1",
    borderRadius: 12,
    padding: 12,
    marginTop: 15,
  },
  stockBannerText: { color: C.green, fontWeight: "900" },
  colorRow: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 11 },
  colorChoice: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 13,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  bigSwatch: {
    width: 27,
    height: 27,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#D5D5D5",
  },
  colorName: { fontSize: 13, fontWeight: "800", color: C.ink },
  optionSelected: {
    borderColor: C.ink,
    borderWidth: 2,
    backgroundColor: "#F8F8F6",
  },
  sizeRow: { flexDirection: "row", flexWrap: "wrap", gap: 9, marginTop: 10 },
  sizeChoice: {
    minWidth: 52,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 10,
    alignItems: "center",
  },
  sizeText: { fontWeight: "800", color: C.ink },
  optionTextSelected: { color: C.dark },
  helperText: { color: C.muted, fontSize: 13, marginTop: 8 },
  wishlistWide: {
    borderWidth: 1,
    borderColor: "#D14343",
    borderRadius: 15,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 12,
  },
  benefits: { flexDirection: "row", gap: 8, marginTop: 25 },
  benefit: {
    flex: 1,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 14,
    padding: 10,
    alignItems: "center",
  },
  benefitIcon: { fontSize: 24 },
  benefitTitle: {
    fontSize: 10,
    fontWeight: "900",
    color: C.ink,
    textAlign: "center",
    marginTop: 6,
  },
  benefitCopy: {
    fontSize: 9,
    color: C.muted,
    textAlign: "center",
    marginTop: 3,
  },
  descriptionBox: {
    backgroundColor: "#F7F8F9",
    borderRadius: 16,
    padding: 16,
    marginTop: 10,
  },
  sectionTitle: {
    fontSize: 17,
    fontWeight: "900",
    color: C.ink,
    marginTop: 24,
  },
  description: { fontSize: 14, lineHeight: 22, color: C.muted, marginTop: 8 },
  variants: { gap: 8, marginTop: 10 },
  variant: {
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 12,
    padding: 12,
    flexDirection: "row",
    alignItems: "center",
  },
  swatch: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 1,
    borderColor: "#ddd",
    marginRight: 8,
  },
  variantText: { flex: 1, fontWeight: "700", color: C.ink },
  variantPrice: { fontWeight: "900", color: C.dark },
  primary: {
    backgroundColor: C.orange,
    borderRadius: 15,
    paddingVertical: 15,
    paddingHorizontal: 24,
    alignItems: "center",
    marginTop: 24,
    minWidth: 220,
  },
  primaryText: { color: "#fff", fontWeight: "900", fontSize: 15 },
  disabled: { opacity: 0.55 },
  outline: {
    borderWidth: 1,
    borderColor: C.orange,
    borderRadius: 14,
    paddingVertical: 12,
    paddingHorizontal: 30,
    marginTop: 20,
  },
  outlineText: { color: C.dark, fontWeight: "800" },
  searchPage: { flex: 1, paddingTop: 20 },
  pageTitle: {
    fontSize: 24,
    fontWeight: "900",
    color: C.ink,
    textAlign: "center",
  },
  searchInput: {
    margin: 18,
    height: 52,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 16,
    paddingHorizontal: 18,
    fontSize: 16,
    color: C.ink,
    backgroundColor: "#FAFAF8",
  },
  emptyPage: {
    flexGrow: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 32,
  },
  emptyIcon: { fontSize: 58, marginBottom: 18 },
  emptyCopy: {
    textAlign: "center",
    fontSize: 14,
    lineHeight: 22,
    color: C.muted,
    maxWidth: 310,
    marginTop: 10,
  },
  accountPage: { padding: 24, alignItems: "center" },
  avatar: {
    width: 84,
    height: 84,
    borderRadius: 28,
    backgroundColor: C.cream,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 24,
    marginBottom: 18,
  },
  avatarText: { fontSize: 42, fontWeight: "900", color: C.orange },
  menuItem: {
    width: "100%",
    paddingVertical: 18,
    borderBottomWidth: 1,
    borderBottomColor: C.line,
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 5,
  },
  menuText: { fontSize: 15, fontWeight: "700", color: C.ink },
  authPage: { flex: 1, backgroundColor: "#fff" },
  authInner: { padding: 24, paddingBottom: 50 },
  authTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  close: { fontSize: 35, color: C.muted },
  authTitle: { fontSize: 30, fontWeight: "900", color: C.ink, marginTop: 32 },
  authCopy: {
    fontSize: 14,
    lineHeight: 21,
    color: C.muted,
    marginTop: 8,
    marginBottom: 15,
  },
  field: { marginTop: 15 },
  fieldLabel: {
    fontSize: 12,
    fontWeight: "800",
    color: C.ink,
    marginBottom: 7,
  },
  fieldInput: {
    height: 52,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 14,
    paddingHorizontal: 15,
    fontSize: 16,
    color: C.ink,
  },
  formMessage: { marginTop: 16, color: C.dark, fontWeight: "700" },
  authSwitch: {
    textAlign: "center",
    color: C.dark,
    fontWeight: "800",
    marginTop: 24,
  },
  cartPage: { padding: 18, paddingBottom: 40 },
  cartRow: {
    flexDirection: "row",
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: C.line,
  },
  cartImage: {
    width: 95,
    height: 110,
    borderRadius: 14,
    backgroundColor: "#F6F4EF",
  },
  cartInfo: { flex: 1, marginLeft: 14 },
  cartName: { fontSize: 15, lineHeight: 20, fontWeight: "800", color: C.ink },
  cartMeta: { fontSize: 12, color: C.muted, marginTop: 5 },
  qty: { flexDirection: "row", alignItems: "center", marginTop: 9 },
  qtyBtn: {
    fontSize: 20,
    fontWeight: "900",
    color: C.dark,
    paddingHorizontal: 9,
  },
  qtyValue: { fontWeight: "900", color: C.ink },
  totalRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingTop: 22,
  },
  totalLabel: { fontSize: 17, fontWeight: "800", color: C.ink },
  totalValue: { fontSize: 20, fontWeight: "900", color: C.dark },
  servicePage: { flex: 1, alignItems: "center", justifyContent: "center" },
  serviceContent: { padding: 18, paddingBottom: 110 },
  serviceTitle: { fontSize: 28, fontWeight: "900", color: C.ink },
  serviceSubtitle: {
    color: C.muted,
    fontSize: 14,
    marginTop: 5,
    marginBottom: 20,
  },
  storeCard: {
    flexDirection: "row",
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 18,
    overflow: "hidden",
    marginBottom: 14,
    backgroundColor: "#fff",
  },
  storeImage: { width: 115, height: 110, resizeMode: "cover" },
  storeFallback: {
    width: 115,
    height: 110,
    backgroundColor: "#E8F7F1",
    alignItems: "center",
    justifyContent: "center",
  },
  storeEmoji: { fontSize: 36 },
  storeCopy: { flex: 1, padding: 14 },
  storeName: { fontSize: 17, fontWeight: "900", color: C.ink },
  storeMeta: { fontSize: 12, color: C.muted, marginTop: 5 },
  groceryGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  groceryCard: {
    width: "48%",
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 16,
    padding: 9,
  },
  groceryImage: {
    height: 125,
    width: "100%",
    borderRadius: 12,
    resizeMode: "cover",
  },
  groceryFallback: {
    height: 125,
    borderRadius: 12,
    backgroundColor: "#F6F4EF",
    alignItems: "center",
    justifyContent: "center",
  },
  groceryName: {
    fontSize: 14,
    fontWeight: "800",
    color: C.ink,
    marginTop: 8,
    minHeight: 38,
  },
  emptyService: { alignItems: "center", paddingVertical: 55 },
  modalHeader: {
    minHeight: 72,
    paddingHorizontal: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderBottomColor: C.line,
  },
  modalTitle: { fontSize: 22, fontWeight: "900", color: C.ink },
  modalContent: { padding: 18, paddingBottom: 45 },
  listCard: {
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 16,
    padding: 15,
    marginBottom: 12,
  },
  listRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  listTitle: { fontSize: 16, fontWeight: "900", color: C.ink },
  listMeta: { fontSize: 12, color: C.muted, marginTop: 7 },
  listPrice: { fontSize: 17, fontWeight: "900", color: C.dark, marginTop: 8 },
  statusPill: {
    fontSize: 11,
    fontWeight: "800",
    color: C.green,
    backgroundColor: "#E8F7F1",
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: 10,
  },
  miniImage: {
    width: 60,
    height: 65,
    borderRadius: 10,
    marginRight: 12,
    backgroundColor: "#F6F4EF",
  },
  listGrow: { flex: 1 },
  removeText: { color: "#B42318", fontWeight: "800", fontSize: 12 },
  addressText: { fontSize: 13, lineHeight: 20, color: C.ink, marginTop: 7 },
  defaultLink: { color: C.green, fontWeight: "800", marginTop: 10 },
  addressForm: { paddingBottom: 20 },
  restaurantHero: {
    height: 190,
    width: "100%",
    borderRadius: 22,
    resizeMode: "cover",
    marginBottom: 18,
  },
  menuCard: {
    flexDirection: "row",
    borderBottomWidth: 1,
    borderBottomColor: C.line,
    paddingVertical: 18,
    gap: 12,
  },
  menuCopy: { flex: 1 },
  menuImage: {
    width: 105,
    height: 105,
    borderRadius: 16,
    backgroundColor: "#F6F4EF",
  },
  openText: { color: C.green, fontWeight: "900", marginTop: 9 },
  stockText: { fontSize: 11, color: C.green, fontWeight: "700", marginTop: 4 },
  stickyCheckout: {
    backgroundColor: C.green,
    borderRadius: 16,
    padding: 17,
    alignItems: "center",
    marginTop: 20,
  },
  checkoutStep: {
    fontSize: 9,
    color: C.green,
    fontWeight: "900",
    letterSpacing: 1,
    marginTop: 3,
  },
  checkoutItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: C.line,
  },
  addressChoice: {
    flexDirection: "row",
    alignItems: "center",
    padding: 14,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 14,
    marginTop: 10,
  },
  addressSelected: { borderColor: C.green, backgroundColor: "#F1FBF6" },
  radio: {
    width: 20,
    height: 20,
    borderWidth: 2,
    borderColor: C.green,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 12,
  },
  radioDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: C.green,
  },
  paymentChoice: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: C.green,
    borderRadius: 14,
    backgroundColor: "#F1FBF6",
    marginTop: 10,
  },
  unselectedChoice: { borderColor: C.line, backgroundColor: "#fff" },
  paymentIcon: { fontSize: 24, fontWeight: "900", color: C.green },
  selectedMark: {
    marginLeft: "auto",
    fontSize: 20,
    color: C.green,
    fontWeight: "900",
  },
  secureNote: { fontSize: 12, lineHeight: 18, color: C.muted, marginTop: 12 },
  currentLocation: {
    flexDirection: "row",
    alignItems: "center",
    gap: 13,
    padding: 16,
    borderRadius: 16,
    backgroundColor: "#E8F7F1",
  },
  locationPin: { fontSize: 28, color: C.green },
  addressIcon: { fontSize: 22, color: C.green, marginRight: 12 },
  chevron: { fontSize: 28, color: C.muted },
  locationInput: {
    height: 54,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 14,
    paddingHorizontal: 16,
    fontSize: 17,
    color: C.ink,
    marginTop: 12,
  },
  cartHub: { padding: 18, paddingBottom: 45 },
  cartTabs: { flexDirection: "row", gap: 8, marginBottom: 18 },
  cartTab: {
    flex: 1,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 15,
    alignItems: "center",
    backgroundColor: "#fff",
  },
  cartTabActive: { borderColor: C.green, backgroundColor: "#E8F7F1" },
  cartTabIcon: { fontSize: 23 },
  cartTabLabel: {
    fontSize: 11,
    fontWeight: "800",
    color: C.muted,
    marginTop: 3,
  },
  cartTabLabelActive: { color: C.green },
  cartTabCount: {
    position: "absolute",
    right: 7,
    top: 6,
    minWidth: 18,
    height: 18,
    lineHeight: 18,
    borderRadius: 9,
    textAlign: "center",
    fontSize: 10,
    fontWeight: "900",
    color: "#fff",
    backgroundColor: C.orange,
  },
  hubRow: {
    flexDirection: "row",
    padding: 14,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 17,
    marginBottom: 11,
    backgroundColor: "#fff",
  },
  hubImage: {
    width: 88,
    height: 98,
    borderRadius: 13,
    backgroundColor: "#F6F4EF",
    marginRight: 13,
  },
  cartSummary: { borderTopWidth: 1, borderTopColor: C.line, marginTop: 10 },
  cartEmpty: { alignItems: "center", paddingVertical: 32 },
});
Object.assign(s, {
  checkoutAddressForm: { paddingTop: 8 },
  addAddressButton: {
    borderWidth: 1,
    borderColor: C.green,
    borderRadius: 14,
    paddingVertical: 13,
    alignItems: "center",
    marginTop: 12,
  },
  addAddressText: { color: C.green, fontWeight: "900" },
  loadingRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 14 },
  quoteError: { backgroundColor: "#FFF2EF", borderRadius: 14, padding: 14, gap: 8 },
  discountText: { color: C.green, fontWeight: "900" },
  confirmBox: { marginTop: 18, padding: 16, borderRadius: 18, backgroundColor: "#F2FAF7", borderWidth: 1, borderColor: "#B8E1D1" },
  centerLink: { color: C.green, fontWeight: "800", textAlign: "center", paddingTop: 14 },
  successBadge: { width: 72, height: 72, borderRadius: 36, alignSelf: "center", alignItems: "center", justifyContent: "center", backgroundColor: C.green, marginTop: 48 },
  successBadgeText: { color: "#fff", fontSize: 38, fontWeight: "900" },
  successTitle: { color: C.ink, fontSize: 30, fontWeight: "900", textAlign: "center", marginTop: 22 },
  successCopy: { color: C.muted, fontSize: 16, lineHeight: 24, textAlign: "center", marginVertical: 12 },
});
