import { appendPhoto } from "./uploads";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Image, Linking, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as FileSystem from "expo-file-system/legacy";
import * as Sharing from "expo-sharing";
import { API_URL, Order, request } from "./api";

type Review = { rating: number; title: string; review: string; approved: boolean };
type Item = { id: number; name: string; quantity: number; can_review: boolean; can_return: boolean; review: Review | null };
type Experience = {
  items: Item[];
  returns: { id: number; order_item_id: number | null; reason: string; status: string; refund_status: string }[];
  shipments: { id: string; seller: string; provider: string; status: string; tracking_number: string; latitude: string | null; longitude: string | null; location_updated_at: string | null }[];
  return_reasons: string[];
  return_deadline: string | null;
  invoice_available: boolean;
};

export default function CustomerOrderTools({ token, order }: { token: string; order: Order }) {
  const [data, setData] = useState<Experience | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [action, setAction] = useState<{ item: Item; type: "review" | "return" } | null>(null);
  const [rating, setRating] = useState(5);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [reason, setReason] = useState("");
  const [image, setImage] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const prefix = `/orders/${order.kind}/${order.id}`;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    request<Experience>(`${prefix}/experience/`, {}, token)
      .then(value => { if (!cancelled) setData(value); })
      .catch(err => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [prefix, token, refresh]);

  const start = (item: Item, type: "review" | "return") => {
    setAction({ item, type });
    setTitle(type === "review" ? item.review?.title || "" : "");
    setText(type === "review" ? item.review?.review || "" : "");
    setRating(item.review?.rating || 5);
    setReason(data?.return_reasons[0] || "Other");
    setImage(null);
    setError("");
  };

  const pickImage = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.7 });
      if (!result.canceled) {
        if ((result.assets[0].fileSize || 0) > 8 * 1024 * 1024) throw new Error("Choose an image smaller than 8 MB.");
        setImage(result.assets[0]);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Could not select an image."); }
  };

  const submit = async () => {
    if (!action || busy) return;
    setBusy(true);
    setError("");
    try {
      if (action.type === "review") {
        await request(`/order-items/${action.item.id}/review/`, {
          method: "POST", body: JSON.stringify({ rating, title, review: text }),
        }, token);
        Alert.alert("Review received", "Your review has been submitted for moderation.");
      } else {
        const payload = new FormData();
        payload.append("order_item_id", String(action.item.id));
        payload.append("reason", reason);
        payload.append("description", text);
        if (image) appendPhoto(payload, "image", image);
        await request(`${prefix}/returns/`, { method: "POST", body: payload }, token);
        Alert.alert("Return requested", "The marketplace team can now review your return. Its status appears below.");
      }
      setAction(null);
      setRefresh(value => value + 1);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not submit your request."); }
    finally { setBusy(false); }
  };

  const shareInvoice = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    const uri = FileSystem.cacheDirectory ? `${FileSystem.cacheDirectory}ZIYAMART-${order.kind}-${order.id}-${Date.now()}.pdf` : null;
    try {
      if (!uri || !(await Sharing.isAvailableAsync())) throw new Error("File sharing is unavailable on this device.");
      const download = await FileSystem.downloadAsync(`${API_URL}${prefix}/invoice/`, uri, {
        headers: { Authorization: `Token ${token}`, Accept: "application/pdf" },
      });
      if (download.status !== 200) throw new Error("Could not download this invoice. Refresh the order or sign in again.");
      await Sharing.shareAsync(uri, { mimeType: "application/pdf", UTI: "com.adobe.pdf", dialogTitle: "Save or share invoice" });
    } catch (err) { setError(err instanceof Error ? err.message : "Could not share invoice."); }
    finally {
      if (uri) await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {});
      setBusy(false);
    }
  }, [busy, order.id, order.kind, prefix, token]);

  return (
    <View style={s.section}>
      <View style={s.row}>
        <Text style={s.heading}>Manage your order</Text>
        <Pressable accessibilityRole="button" disabled={loading || busy} onPress={() => setRefresh(n => n + 1)}>
          <Text style={s.link}>Refresh</Text>
        </Pressable>
      </View>
      {loading && <ActivityIndicator color="#C84E1F" />}
      {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
      {data?.invoice_available && (
        <Pressable style={s.button} disabled={busy} onPress={shareInvoice}>
          <Text style={s.buttonText}>{busy ? "Please wait…" : "Download / share invoice"}</Text>
        </Pressable>
      )}
      {data?.shipments.map(shipment => (
        <View key={shipment.id} style={s.card}>
          <Text style={s.heading}>{shipment.seller}</Text>
          <Text style={s.body}>{shipment.provider} · {shipment.status.replace(/_/g, " ")}</Text>
          {!!shipment.tracking_number && <Text selectable style={s.body}>Tracking: {shipment.tracking_number}</Text>}
          {shipment.latitude !== null && shipment.longitude !== null && (
            <Pressable accessibilityRole="button" onPress={() => {
              Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${shipment.latitude},${shipment.longitude}`)}`).catch(err => setError(err.message));
            }}><Text style={s.link}>View rider’s last shared location</Text></Pressable>
          )}
          {shipment.location_updated_at && <Text style={s.note}>Updated {new Date(shipment.location_updated_at).toLocaleString()}</Text>}
        </View>
      ))}
      {data?.items.filter(item => item.can_review || item.can_return || item.review).map(item => (
        <View key={item.id} style={s.card}>
          <Text style={s.heading}>{item.name}</Text>
          {item.review && <Text style={s.note}>{item.review.rating}/5 · Review {item.review.approved ? "published" : "awaiting moderation"}</Text>}
          <View style={s.row}>
            {item.can_review && <Pressable disabled={busy} onPress={() => start(item, "review")}><Text style={s.link}>{item.review ? "Edit review" : "Write a review"}</Text></Pressable>}
            {item.can_return && <Pressable disabled={busy} onPress={() => start(item, "return")}><Text style={s.link}>Return this item</Text></Pressable>}
          </View>
        </View>
      ))}
      {action && (
        <View style={s.card}>
          <Text style={s.heading}>{action.type === "review" ? "Your review" : "Return request"}: {action.item.name}</Text>
          {action.type === "review" ? (
            <>
              <View style={s.row}>{[1, 2, 3, 4, 5].map(value => (
                <Pressable key={value} accessibilityRole="radio" accessibilityLabel={`${value} stars`} accessibilityState={{ selected: rating === value }} disabled={busy} onPress={() => setRating(value)}>
                  <Text style={[s.star, value <= rating && s.starSelected]}>★</Text>
                </Pressable>
              ))}</View>
              <TextInput style={s.input} accessibilityLabel="Review title" placeholder="Review title (optional)" value={title} onChangeText={setTitle} maxLength={100} editable={!busy} />
            </>
          ) : (
            <>
              <Text style={s.note}>This request covers all {action.item.quantity} units of this order item.</Text>
              <View style={s.row}>{data?.return_reasons.map(value => (
                <Pressable key={value} disabled={busy} style={[s.choice, reason === value && s.chosen]} onPress={() => setReason(value)}>
                  <Text style={s.body}>{value}</Text>
                </Pressable>
              ))}</View>
              <Pressable disabled={busy} onPress={pickImage}><Text style={s.link}>{image ? "Change evidence photo" : "Attach evidence photo (optional)"}</Text></Pressable>
              {image && <Image source={{ uri: image.uri }} style={s.photo} />}
            </>
          )}
          <TextInput style={[s.input, s.multiline]} multiline accessibilityLabel={action.type === "review" ? "Review text" : "Return description"} placeholder="Tell us more (at least 5 characters)" maxLength={5000} value={text} onChangeText={setText} editable={!busy} />
          <Pressable style={[s.button, (busy || text.trim().length < 5) && s.disabled]} disabled={busy || text.trim().length < 5} onPress={submit}>
            <Text style={s.buttonText}>{busy ? "Submitting…" : "Submit"}</Text>
          </Pressable>
          <Pressable disabled={busy} onPress={() => setAction(null)}><Text style={s.link}>Cancel</Text></Pressable>
        </View>
      )}
      {data?.returns.map(row => (
        <View style={s.card} key={row.id}>
          <Text style={s.heading}>Return #{row.id} · {row.status}</Text>
          <Text style={s.body}>{data.items.find(item => item.id === row.order_item_id)?.name || "Order return"} · {row.reason}</Text>
          <Text style={s.note}>Refund: {row.refund_status}</Text>
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  section: { gap: 14, marginVertical: 15 }, row: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12 },
  heading: { fontSize: 16, fontWeight: "700", color: "#17243A", flexShrink: 1 }, body: { color: "#17243A", lineHeight: 21 }, note: { color: "#5D6B7D", lineHeight: 20 },
  card: { padding: 15, gap: 12, borderWidth: 1, borderColor: "#E3DED6", borderRadius: 14, backgroundColor: "#FFFCF7" },
  link: { color: "#A83D16", fontWeight: "700", paddingVertical: 10 }, button: { backgroundColor: "#C84E1F", padding: 14, borderRadius: 12, alignItems: "center" },
  buttonText: { color: "white", fontWeight: "700" }, disabled: { opacity: 0.4 }, error: { color: "#AF2424", lineHeight: 22 },
  input: { borderWidth: 1, borderColor: "#BDC7D1", borderRadius: 10, padding: 12, color: "#17243A", backgroundColor: "white" }, multiline: { minHeight: 100, textAlignVertical: "top" },
  star: { fontSize: 35, color: "#A0A8B2", padding: 2 }, starSelected: { color: "#A56A00" }, choice: { padding: 10, borderWidth: 1, borderColor: "#D0D5DD", borderRadius: 10 }, chosen: { backgroundColor: "#FFE5D4", borderColor: "#C84E1F" }, photo: { width: 100, height: 100, borderRadius: 8 },
});
