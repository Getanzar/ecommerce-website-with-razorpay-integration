import { useMemo, useState } from "react";
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from "react-native";
import { getGroceryProducts, GroceryProduct, GroceryStore } from "./api";
import { createStoreCatalog } from "./groceryCatalog";
import { useCatalog } from "./useCatalog";
import { DeliveryInterestForm } from "./FoodDiscovery";

type Group = { id: number; name: string; slug: string; image_url?: string | null };
type Props = {
  pincode: string; stores: GroceryStore[]; groups: Group[]; error: string;
  token: string | null;
  cartCount: number; onCart: () => void; onLocation: () => void;
  onProduct: (product: GroceryProduct) => void;
};

export default function GroceryDiscovery({ pincode, stores, groups, error, token, cartCount, onCart, onLocation, onProduct }: Props) {
  const { width } = useWindowDimensions();
  const contentWidth = Math.min(width, 720) - 32;
  const categoryWidth = (contentWidth - 24) / 3;
  const cardWidth = (contentWidth - 12) / 2;
  const [selected, setSelected] = useState<Group | null>(null);
  const [query, setQuery] = useState("");
  const storeKey = stores.map(store => store.slug).join(",");
  const fetchPreview = useMemo(() => createStoreCatalog<GroceryProduct>(stores.map(store => store.slug),
    (store, page, signal) => getGroceryProducts({ store, page: String(page) }, signal)), [storeKey]);
  const preview = useCatalog<GroceryProduct>(`grocery-preview:${pincode}:${storeKey}`, fetchPreview, !!pincode && stores.length > 0);
  const fetchProducts = useMemo(() => createStoreCatalog<GroceryProduct>(stores.map(store => store.slug),
    (store, page, signal) => getGroceryProducts({ store, category: selected?.slug, q: query.trim(), page: String(page) }, signal)), [storeKey, selected?.slug, query]);
  const catalog = useCatalog<GroceryProduct>(JSON.stringify(["grocery-category", pincode, storeKey, selected?.slug, query]), fetchProducts, !!selected && !!pincode && stores.length > 0);
  const money = (value: string) => `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  return <ScrollView style={g.screen} contentContainerStyle={g.page} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
    {selected ? <>
      <Pressable accessibilityRole="button" onPress={() => { setSelected(null); setQuery(""); }} style={g.back}><Text style={g.link}>‹ All grocery categories</Text></Pressable>
      <Text style={g.eyebrow}>DELIVERING TO {pincode}</Text>
      <Text style={g.title}>{selected.name}</Text>
      <Text style={g.subtitle}>Your essentials from local sellers.</Text>
      <TextInput accessibilityLabel={`Search ${selected.name}`} placeholder="Search essentials" placeholderTextColor="#66746A" value={query} onChangeText={setQuery} style={g.search} />
      <View style={g.notice}><Text style={g.noticeText}>Free delivery on orders of ₹200 or more. One store per order.</Text></View>
      {catalog.loading && <ActivityIndicator color="#17634A" style={g.loading} />}
      <View style={g.grid}>{catalog.items.map(product => <Pressable key={product.id} accessibilityRole="button" accessibilityLabel={`${product.name}, ${money(product.price_with_tax || product.price)}, choose pack`} style={[g.product, { width: cardWidth }]} onPress={() => onProduct(product)}>
        <View style={g.productPhoto}>{product.image_url ? <Image source={{ uri: product.image_url }} style={g.photo} /> : <Text style={g.placeholder}>🥬</Text>}</View>
        <View style={g.productBody}>
          <Text style={g.unit} numberOfLines={1}>{product.brand ? `${product.brand} · ` : ""}{product.unit}</Text>
          <Text style={g.productName} numberOfLines={2}>{product.name}</Text>
          <Text style={g.seller} numberOfLines={1}>{product.store_name}</Text>
          <View style={g.productBottom}><Text style={g.price}>{money(product.price_with_tax || product.price)}</Text>{Number(product.mrp) > Number(product.price_with_tax || product.price) && <Text style={g.mrp}>{money(product.mrp)}</Text>}<Text style={g.tax}>Inclusive of taxes</Text><Text style={g.add}>Choose pack +</Text></View>
        </View>
      </Pressable>)}</View>
      {!!catalog.error && <View style={g.empty}><Text style={g.subtitle}>{catalog.error}</Text><Pressable style={g.button} onPress={() => void (catalog.items.length ? catalog.more() : catalog.refresh())}><Text style={g.buttonText}>Try again</Text></Pressable></View>}
      {catalog.hasNext && !catalog.error && <Pressable disabled={catalog.loadingMore} style={g.more} onPress={() => void catalog.more()}>{catalog.loadingMore ? <ActivityIndicator color="#17634A" /> : <Text style={g.link}>Load more essentials ↓</Text>}</Pressable>}
      {!catalog.loading && !catalog.error && !catalog.items.length && <View style={g.empty}><Text style={g.emptyTitle}>No essentials found</Text><Text style={g.subtitle}>Try another search or explore another category.</Text></View>}
    </> : <>
      <View style={g.hero}>
        <Text style={g.eyebrow}>YOUR EVERYDAY ESSENTIALS</Text>
        <Text style={g.heroTitle}>A fresh way to shop{`\n`}your neighbourhood.</Text>
        <Text style={g.subtitle}>From vegetables to atta, find what you need by category.</Text>
        <Text style={g.locationLabel}>Where should we deliver?</Text>
        <Pressable accessibilityRole="button" onPress={onLocation} style={g.location}><Text style={g.locationText}>{pincode ? `Delivering to ${pincode}` : "Choose delivery pincode"}</Text><Text style={g.link}>{pincode ? "Change" : "Select"} →</Text></Pressable>
        <View style={g.perk}><Text style={g.perkTitle}>Free delivery</Text><Text style={g.perkCopy}>on orders of ₹200 or more</Text></View>
      </View>
      {!!pincode && stores.length > 0 && <>
        <View style={g.section}><Text style={g.eyebrow}>DELIVERING TO {pincode}</Text><Text style={g.title}>Shop by category</Text><Text style={g.subtitle}>Pick your essentials. Discover local sellers.</Text></View>
        {preview.loading && <ActivityIndicator color="#17634A" style={g.loading} />}
        <View style={g.grid}>{groups.map(group => {
          const photos = preview.items.filter(product => product.category.slug === group.slug && product.image_url).slice(0, 4).map(product => product.image_url!);
          if (!photos.length && group.image_url) photos.push(group.image_url);
          return <Pressable key={group.id} accessibilityRole="button" accessibilityLabel={`Shop ${group.name}`} onPress={() => setSelected(group)} style={[g.category, { width: categoryWidth }]}>
            <View style={g.collage}>{photos.length ? photos.map((uri, index) => <Image key={`${uri}:${index}`} source={{ uri }} style={[g.collageImage, { width: photos.length === 1 ? "100%" : "46%", height: photos.length < 3 ? "100%" : "46%" }]} />) : <Text style={g.placeholder}>🥬</Text>}<View style={g.arrow}><Text style={g.link}>↗</Text></View></View>
            <Text style={g.categoryName} numberOfLines={2}>{group.name}</Text><Text style={g.categoryCopy}>Explore essentials</Text>
          </Pressable>;
        })}</View>
        {!preview.loading && !!preview.error && <Pressable style={g.more} onPress={() => void preview.refresh()}><Text style={g.link}>Retry category photos</Text></Pressable>}
        {!groups.length && <View style={g.empty}><Text style={g.emptyTitle}>New essentials are on their way</Text><Text style={g.subtitle}>Check back soon for available categories.</Text></View>}
      </>}
      {!!error && <View style={g.empty}><Text style={g.emptyTitle}>Groceries could not be loaded</Text><Text style={g.subtitle}>{error}</Text><Pressable onPress={onLocation} style={g.button}><Text style={g.buttonText}>Check delivery location</Text></Pressable></View>}
      {!error && (!pincode || !stores.length) && <View style={g.empty}><Text style={g.emptyTitle}>{pincode ? "We're not in your area yet" : "Start with your delivery pincode"}</Text><Text style={g.subtitle}>{pincode ? `Groceries aren't currently available at ${pincode}. Try another delivery pincode.` : "We'll show essentials from sellers who deliver to you."}</Text><Pressable onPress={onLocation} style={g.button}><Text style={g.buttonText}>{pincode ? "Try another pincode" : "Choose delivery location"}</Text></Pressable></View>}
      {!error && !!pincode && !stores.length && <DeliveryInterestForm service="grocery" pincode={pincode} token={token} />}
    </>}
    {cartCount > 0 && <Pressable accessibilityRole="button" onPress={onCart} style={g.cart}><Text style={g.buttonText}>{cartCount} {cartCount === 1 ? "item" : "items"} · Your grocery cart →</Text></Pressable>}
  </ScrollView>;
}

const g = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#FAFBF8" },
  page: { width: "100%", maxWidth: 720, alignSelf: "center", padding: 16, paddingBottom: 32 },
  hero: { backgroundColor: "#EDF4E8", borderWidth: 1, borderColor: "#E0EAD9", borderRadius: 20, padding: 20 },
  eyebrow: { fontSize: 10, letterSpacing: 1.5, fontWeight: "700", color: "#17634A", marginBottom: 10 },
  heroTitle: { fontSize: 28, lineHeight: 34, letterSpacing: -0.8, fontWeight: "700", color: "#182B20", marginBottom: 10 },
  subtitle: { fontSize: 13, lineHeight: 20, color: "#66746A", marginTop: 6 },
  locationLabel: { color: "#182B20", fontSize: 12, fontWeight: "600", marginTop: 20, marginBottom: 8 },
  location: { padding: 12, minHeight: 48, backgroundColor: "#FFF", borderWidth: 1, borderColor: "#DCE6D7", borderRadius: 10, flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 },
  locationText: { fontSize: 13, color: "#182B20", fontWeight: "600", flexShrink: 1 },
  link: { fontSize: 12, color: "#17634A", fontWeight: "700" },
  perk: { marginTop: 16, paddingTop: 14, borderTopWidth: 1, borderTopColor: "#DCE6D7", gap: 3 },
  perkTitle: { color: "#182B20", fontSize: 16, fontWeight: "700" },
  perkCopy: { color: "#66746A", fontSize: 12 },
  section: { marginTop: 28, marginBottom: 20 },
  title: { color: "#182B20", fontSize: 24, lineHeight: 30, fontWeight: "700", letterSpacing: -0.5 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12, alignItems: "stretch" },
  category: { marginBottom: 10, alignItems: "center" },
  collage: { width: "100%", aspectRatio: 1, backgroundColor: "#F1F4ED", borderWidth: 1, borderColor: "#E1E8E0", borderRadius: 14, padding: 8, flexDirection: "row", flexWrap: "wrap", justifyContent: "center", alignItems: "center", gap: 4, overflow: "hidden" },
  collageImage: { resizeMode: "contain", borderRadius: 6 },
  arrow: { position: "absolute", bottom: 6, right: 6, width: 24, height: 24, borderRadius: 12, backgroundColor: "white", alignItems: "center", justifyContent: "center" },
  categoryName: { fontSize: 12, lineHeight: 17, fontWeight: "600", color: "#182B20", marginTop: 10, textAlign: "center" },
  categoryCopy: { color: "#66746A", fontSize: 10, marginTop: 4, textAlign: "center" },
  back: { minHeight: 44, justifyContent: "center", alignSelf: "flex-start", marginBottom: 12 },
  search: { minHeight: 48, marginTop: 20, marginBottom: 12, borderWidth: 1, borderColor: "#E1E8E0", borderRadius: 10, backgroundColor: "white", paddingHorizontal: 14, color: "#182B20", fontSize: 14 },
  notice: { padding: 12, backgroundColor: "#EFF4EC", borderRadius: 10, marginBottom: 20 },
  noticeText: { fontSize: 11, lineHeight: 17, color: "#526658" },
  product: { borderWidth: 1, borderColor: "#E1E8E0", borderRadius: 16, backgroundColor: "white", overflow: "hidden" },
  productPhoto: { aspectRatio: 1, padding: 12, backgroundColor: "#F7F8F4", alignItems: "center", justifyContent: "center" },
  photo: { width: "100%", height: "100%", resizeMode: "contain" },
  placeholder: { fontSize: 32 },
  productBody: { padding: 12, flex: 1 },
  unit: { fontSize: 10, color: "#66746A" },
  productName: { fontSize: 13, lineHeight: 19, minHeight: 38, fontWeight: "700", color: "#182B20", marginVertical: 7 },
  seller: { fontSize: 11, color: "#17634A", marginBottom: 14 },
  productBottom: { marginTop: "auto" },
  price: { fontSize: 17, fontWeight: "700", color: "#182B20" },
  mrp: { fontSize: 11, color: "#66746A", textDecorationLine: "line-through", marginTop: 3 },
  tax: { fontSize: 10, color: "#66746A", marginTop: 4 },
  add: { textAlign: "center", paddingVertical: 12, marginTop: 12, borderWidth: 1, borderColor: "#BDCFBC", borderRadius: 9, backgroundColor: "#F3F8EE", color: "#17634A", fontSize: 12, fontWeight: "700" },
  empty: { padding: 24, marginTop: 20, borderWidth: 1, borderColor: "#E1E8E0", borderRadius: 16, backgroundColor: "white" },
  emptyTitle: { color: "#182B20", fontWeight: "700", fontSize: 19, lineHeight: 25 },
  button: { alignSelf: "flex-start", backgroundColor: "#17634A", borderRadius: 10, padding: 14, marginTop: 16 },
  buttonText: { color: "white", fontWeight: "700", fontSize: 13 },
  more: { padding: 16, minHeight: 48, alignItems: "center", marginTop: 16 },
  cart: { backgroundColor: "#17634A", padding: 16, borderRadius: 12, marginTop: 24, alignItems: "center" },
  loading: { marginVertical: 20 },
});
