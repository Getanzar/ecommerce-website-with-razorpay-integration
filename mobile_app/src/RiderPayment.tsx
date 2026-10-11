import { useEffect, useState } from "react";
import { Alert, Image, Pressable, StyleSheet, Text, View } from "react-native";
import { Collection, Job, partnerRequest } from "./partnerApi";

export default function RiderPayment({ row, token, onPaid }: { row: Job; token: string; onPaid: () => void }) {
  const [payment, setPayment] = useState<Collection>(row.collection);
  const [busy, setBusy] = useState(false);
  const [cash, setCash] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setPayment(row.collection); }, [row.collection]);
  const act = async (action: "cash" | "online" | "check") => {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const result = await partnerRequest<Collection>(token, `rider/jobs/${row.id}/payment/`, "POST", { action, confirmed: action === "cash" });
      setPayment(result);
      if (result.paid) onPaid();
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to confirm payment."); }
    finally { setBusy(false); }
  };
  const amount = `Rs. ${payment.amount_due}`;
  return <View style={s.panel}>
    <Text style={s.title}>{payment.paid ? `Paid ${payment.method === "cash" ? "in cash" : "online"}` : `COD - collect ${amount}`}</Text>
    {payment.paid && payment.method === "cash" && <Text>Cash recorded in your remittance balance.</Text>}
    {!payment.paid && row.status === "out_for_delivery" && <>
      <View style={s.row}>
        <Pressable accessibilityRole="button" disabled={busy} onPress={() => setCash(true)} style={s.button}><Text style={s.buttonText}>Cash</Text></Pressable>
        <Pressable accessibilityRole="button" disabled={busy} onPress={() => { setCash(false); void act("online"); }} style={s.button}><Text style={s.buttonText}>Pay online</Text></Pressable>
      </View>
      {cash && <Pressable accessibilityRole="button" disabled={busy} style={s.button} onPress={() => Alert.alert("Confirm cash received", `Has the customer given you ${amount}?`, [{ text: "Back", style: "cancel" }, { text: "Mark paid", onPress: () => void act("cash") }])}><Text style={s.buttonText}>Mark cash received</Text></Pressable>}
      {!!payment.qr_image_url && <>
        <Text style={s.title}>Pay ZIYAMART - {amount}</Text>
        <Image accessibilityLabel={`ZIYAMART payment QR for ${amount}`} source={{ uri: payment.qr_image_url }} style={s.qr} resizeMode="contain" />
        <Text>Waiting for payment confirmation.</Text>
        <Pressable accessibilityRole="button" disabled={busy} style={s.button} onPress={() => void act("check")}><Text style={s.buttonText}>{busy ? "Checking..." : "Check payment status"}</Text></Pressable>
      </>}
    </>}
    {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
  </View>;
}

const s = StyleSheet.create({ panel: { gap: 10, borderTopWidth: 1, borderColor: "#C7CFD8", paddingTop: 12 }, row: { flexDirection: "row", gap: 10, flexWrap: "wrap" }, title: { fontSize: 16, fontWeight: "700", color: "#17243A" }, button: { padding: 14, backgroundColor: "#0A765C", borderRadius: 8, minHeight: 48 }, buttonText: { color: "white", fontWeight: "700" }, qr: { width: "100%", maxWidth: 320, aspectRatio: 1, alignSelf: "center", backgroundColor: "white" }, error: { color: "#B32929" } });
