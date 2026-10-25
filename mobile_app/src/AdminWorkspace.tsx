import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as WebBrowser from "expo-web-browser";
import { API_URL, request } from "./api";

type Overview = {
  metrics: Record<string, number>;
  pending_products: { id: number; name: string; seller__store_name: string | null }[];
  pending_sellers: { id: number; store_name: string; business_segment: string }[];
};
const portals = [
  ["Operations dashboard", "/dashboard/"],
  ["Orders and fulfilment", "/dashboard/operations/orders/"],
  ["Seller review", "/dashboard/sellers/"],
  ["Product moderation", "/dashboard/products/"],
  ["Customers", "/dashboard/operations/customers/"],
  ["Riders", "/dashboard/operations/agents/"],
  ["Deliveries", "/dashboard/operations/deliveries/"],
  ["Settlements and payouts", "/dashboard/operations/payouts/"],
  ["Returns", "/dashboard/returns/"],
  ["Support", "/dashboard/support/"],
  ["Categories", "/dashboard/categories/"],
  ["Account deletion and seller cases", "/admin/"],
] as const;

export default function AdminWorkspace({ token, onClose }: { token: string; onClose: () => void }) {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setError(""); setData(null);
    request<Overview>("/operations/", {}, token).then(value => { if (active) setData(value); }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [token, retry]);
  const open = async (path: string) => {
    try {
      // Browser authentication is separate. Never put device tokens in URLs.
      await WebBrowser.openBrowserAsync(`${API_URL.replace(/\/api\/v1$/, "")}${path}`);
      setRetry(n => n + 1);
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to open operations."); }
  };
  return <Modal visible animationType="slide" onRequestClose={onClose}><SafeAreaView style={s.screen}>
    <View style={s.header}><Text style={s.title}>ZIYAMART Operations</Text><Pressable accessibilityRole="button" onPress={onClose}><Text style={s.link}>Close</Text></Pressable></View>
    <ScrollView contentContainerStyle={s.content}>
      {!!error && <View style={s.card}><Text accessibilityRole="alert">{error}</Text><Pressable accessibilityRole="button" onPress={() => setRetry(n => n + 1)}><Text style={s.link}>Retry</Text></Pressable></View>}
      {!data && !error && <ActivityIndicator />}
      {data && <>
        <View style={s.grid}>{Object.entries(data.metrics).map(([label, count]) => <View style={s.metric} key={label}><Text style={s.caption}>{label.replace(/_/g, " ")}</Text><Text style={s.number}>{count}</Text></View>)}</View>
        <View style={s.card}><Text style={s.title}>Needs review</Text>{data.pending_products.map(row => <Text key={`p${row.id}`} style={s.line}>Product #{row.id} · {row.name} · {row.seller__store_name || "Marketplace"}</Text>)}{data.pending_sellers.map(row => <Text key={`s${row.id}`} style={s.line}>Seller #{row.id} · {row.store_name}</Text>)}{!data.pending_products.length && !data.pending_sellers.length && <Text style={s.line}>No sellers or products are waiting for review.</Text>}</View>
        <View style={s.card}><Text style={s.title}>Manage marketplace</Text><Text style={s.line}>Management actions open the secure website. Sign in with your administrator account; your normal permissions and audit history apply.</Text>{portals.map(([name, path]) => <Pressable accessibilityRole="button" style={s.action} key={path} onPress={() => void open(path)}><Text style={s.link}>{name} →</Text></Pressable>)}</View>
      </>}
    </ScrollView>
  </SafeAreaView></Modal>;
}
const s = StyleSheet.create({ screen: { flex: 1, backgroundColor: "#F5F7FA" }, header: { padding: 20, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 }, title: { fontSize: 20, fontWeight: "800", color: "#17243A" }, content: { padding: 20, gap: 18 }, card: { backgroundColor: "white", padding: 20, borderRadius: 16, gap: 12 }, grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 }, metric: { flexGrow: 1, minWidth: "42%", backgroundColor: "#17243A", padding: 20, borderRadius: 16 }, caption: { color: "#DDE7F3", textTransform: "capitalize" }, number: { color: "white", fontWeight: "800", fontSize: 30, marginTop: 8 }, line: { color: "#526175", lineHeight: 22 }, link: { color: "#A5411C", fontWeight: "700", paddingVertical: 10 }, action: { borderBottomWidth: 1, borderBottomColor: "#EBEFF4", minHeight: 44 } });
