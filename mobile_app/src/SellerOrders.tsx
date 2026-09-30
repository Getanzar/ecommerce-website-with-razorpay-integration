import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Modal, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Kind, Page, partnerRequest, SellerOrder } from "./partnerApi";
import { SellerCases } from "./PartnerExceptions";

const money = (value: string) => `₹${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const label = (value: string) => value.replace(/_/g, " ");

export function SellerOrderRow({ order, onOpen }: { order: SellerOrder; onOpen: () => void }) {
  const count = order.items.reduce((sum, item) => sum + item.quantity, 0);
  return <Pressable accessibilityRole="button" accessibilityLabel={`Open order ${order.order_id}, ${label(order.status)}`} onPress={onOpen} style={s.card}>
    <View style={s.row}><Text style={s.heading}>Order #{order.order_id}</Text><Text style={[s.status, order.status === "cancelled" && s.error]}>{label(order.status)}</Text></View>
    <Text style={s.body}>{order.customer}</Text>
    <Text numberOfLines={1} style={s.muted}>{order.items.map(item => item.name).join(", ")}</Text>
    <View style={s.row}><Text style={s.muted}>{count} {count === 1 ? "item" : "items"} · {order.payment_method.toUpperCase()}</Text><Text style={s.amount}>{money(order.amount)}</Text></View>
    <View style={s.row}><Text style={s.muted}>{new Date(order.created_at).toLocaleString()}</Text><Text style={s.link}>View order ›</Text></View>
  </Pressable>;
}

function Action({ title, onPress, disabled, secondary }: { title: string; onPress: () => void; disabled?: boolean; secondary?: boolean }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled: !!disabled }} disabled={disabled} onPress={onPress} style={[s.button, secondary && s.secondary, disabled && s.disabled]}><Text style={[s.buttonText, secondary && s.body]}>{title}</Text></Pressable>;
}

function OrderActions({ row, token, onChanged }: { row: SellerOrder; token: string; onChanged: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const acting = useRef(false);
  const [reason, setReason] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [history, setHistory] = useState(false);
  const [courier, setCourier] = useState(row.courier);
  const [tracking, setTracking] = useState(row.tracking_number);
  const [error, setError] = useState("");
  const itemScope = row.kind === "shop";
  const cancelLabel = ["new", "placed"].includes(row.status) ? "Reject" : "Cancel";
  const act = async (cancel: boolean) => {
    if (acting.current) return;
    acting.current = true; setBusy(true); setError("");
    try {
      if (cancel) {
        const result = await partnerRequest<{ message: string }>(token, `seller/${row.kind}/orders/${row.id}/cancel/`, "POST", { reason: reason.trim() });
        setCancelling(false); setReason(""); Alert.alert("Cancellation status", result.message);
      } else {
        await partnerRequest(token, `seller/${row.kind}/orders/${row.id}/`, "PATCH", { status: row.next_status, courier, tracking_number: tracking });
      }
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update this order. Refresh and try again.");
      await onChanged();
    } finally { acting.current = false; setBusy(false); }
  };
  return <View style={s.card}>
    {row.items.map((item, index) => <View key={index} style={s.item}><Text style={s.heading}>{item.quantity} × {item.name}</Text>{!!item.variant && <Text style={s.muted}>{item.variant}</Text>}</View>)}
    <View style={s.row}><Text style={[s.status, row.status === "cancelled" && s.error]}>{label(row.status)}</Text><Text style={s.amount}>{money(row.amount)}</Text></View>
    {itemScope && <Text style={s.muted}>Actions below apply to this item only.</Text>}
    {!!row.courier && <Text style={s.muted}>Courier: {row.courier} · {row.tracking_number}</Text>}
    {row.next_status === "shipped" && <>
      <TextInput accessibilityLabel="Courier" placeholder="Courier" value={courier} onChangeText={setCourier} style={s.input} />
      <TextInput accessibilityLabel="Tracking number" placeholder="Tracking number" value={tracking} onChangeText={setTracking} style={s.input} />
    </>}
    {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
    {!!row.next_status && <Action title={busy ? "Saving…" : row.next_status === "accepted" ? `Confirm ${itemScope ? "item" : "order"}` : `Mark ${label(row.next_status)}`} disabled={busy || (row.next_status === "shipped" && (!courier.trim() || !tracking.trim()))} onPress={() => act(false)} />}
    {row.can_cancel && <Action secondary title={`${cancelLabel} ${itemScope ? "item" : "order"}`} disabled={busy} onPress={() => setCancelling(!cancelling)} />}
    {row.can_cancel && cancelling && <View style={s.item}>
      <Text style={s.body}>Reason for {cancelLabel === "Reject" ? "rejection" : "cancellation"}</Text>
      <TextInput accessibilityLabel="Cancellation reason" placeholder="Explain why (at least 5 characters)" value={reason} onChangeText={setReason} maxLength={1000} multiline style={s.input} />
      {row.payment_method === "online" && <Text style={s.muted}>Paid orders require a refund. Refund status may remain pending until the payment provider confirms it.</Text>}
      <Action title={`Confirm ${cancelLabel.toLowerCase()}`} disabled={busy || reason.trim().length < 5} onPress={() => Alert.alert(`${cancelLabel} ${itemScope ? "this item" : "this order"}?`, "This stops fulfilment and restores eligible stock. This action cannot be undone.", [{ text: "Keep order", style: "cancel" }, { text: cancelLabel, style: "destructive", onPress: () => act(true) }])} />
    </View>}
    {!row.next_status && !["cancelled", "delivered"].includes(row.status) && <Text style={s.muted}>Awaiting payment or delivery updates. Fulfilment and payment checks apply to all changes.</Text>}
    <Action secondary title={history ? "Hide requests & history" : "Requests & history"} onPress={() => setHistory(!history)} />
    {history && <SellerCases token={token} kind={row.kind} id={row.id} />}
  </View>;
}

export function SellerOrderDetail({ token, kind, orderId, onClose, onChanged }: { token: string; kind: Kind; orderId: number; onClose: () => void; onChanged: () => void }) {
  const [rows, setRows] = useState<SellerOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true); setError("");
    try {
      const details: SellerOrder[] = [];
      let page = 1;
      while (true) {
        const result = await partnerRequest<Page<SellerOrder>>(token, `seller/${kind}/orders/?order_id=${orderId}&page=${page}`);
        if (current !== generation.current) return;
        details.push(...result.results);
        if (!result.next) break;
        page++;
      }
      setRows(details);
    } catch (e) { if (current === generation.current) { setRows([]); setError(e instanceof Error ? e.message : "Unable to load order."); } }
    finally { if (current === generation.current) setLoading(false); }
  }, [token, kind, orderId]);
  useEffect(() => { load(); return () => { generation.current++; }; }, [load]);
  const first = rows[0];
  return <Modal visible animationType="slide" onRequestClose={onClose}><SafeAreaView style={s.screen}>
    <View style={s.header}><View><Text style={s.muted}>SELLER ORDER</Text><Text style={s.title}>Order #{orderId}</Text></View><Action secondary title="Back to orders" onPress={onClose} /></View>
    <ScrollView contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />} keyboardShouldPersistTaps="handled">
      {!!error && <View style={s.card}><Text accessibilityRole="alert" style={s.error}>{error}</Text><Action title="Retry" onPress={load} /></View>}
      {loading && <ActivityIndicator color="#C84E1F" />}
      {first && <View style={s.card}><Text style={s.heading}>{first.customer}</Text><Text style={s.body}>{first.address}</Text><Text style={s.muted}>{new Date(first.created_at).toLocaleString()}</Text><Text style={s.body}>{first.payment_method.toUpperCase()} · {first.payment_status}</Text><View style={s.row}><Text style={s.muted}>Your items total</Text><Text style={s.amount}>{money(String(rows.reduce((sum, row) => sum + Number(row.amount), 0)))}</Text></View>{kind === "shop" && <Text style={s.muted}>Only your store’s items are shown. Other sellers’ items are unaffected.</Text>}</View>}
      {!loading && !error && !rows.length && <Text style={s.muted}>This order is no longer available to your seller account.</Text>}
      {rows.map(row => <OrderActions key={row.id} row={row} token={token} onChanged={async () => { await load(); onChanged(); }} />)}
    </ScrollView>
  </SafeAreaView></Modal>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#FFF8EF" }, content: { padding: 18, gap: 12, paddingBottom: 40 },
  header: { padding: 18, borderBottomWidth: 1, borderColor: "#E9E2D8", flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" },
  title: { color: "#17243A", fontSize: 23, fontWeight: "800" }, heading: { color: "#17243A", fontSize: 16, fontWeight: "700", flexShrink: 1 },
  card: { backgroundColor: "white", padding: 16, borderRadius: 14, borderWidth: 1, borderColor: "#E9E2D8", gap: 9 },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }, item: { gap: 10 },
  body: { color: "#17243A", fontSize: 15 }, muted: { color: "#5D6B7D", fontSize: 13, lineHeight: 20 }, amount: { color: "#17243A", fontSize: 18, fontWeight: "800" },
  status: { color: "#0A765C", fontSize: 13, fontWeight: "700", textTransform: "capitalize" }, link: { color: "#B04B1F", fontWeight: "700" }, error: { color: "#B32929", lineHeight: 21 },
  input: { borderWidth: 1, borderColor: "#C7CFD8", padding: 12, borderRadius: 10, minHeight: 48, color: "#17243A" },
  button: { backgroundColor: "#C84E1F", borderRadius: 10, padding: 14, minHeight: 48, alignItems: "center" }, buttonText: { color: "white", fontWeight: "700" }, secondary: { backgroundColor: "#F2EDE5" }, disabled: { opacity: 0.45 },
});
