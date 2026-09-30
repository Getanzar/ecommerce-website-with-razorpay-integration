import { appendPhoto } from "./uploads";
import React, { useEffect, useState } from "react";
import { Alert, Pressable, Text, TextInput, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { request } from "./api";

export function SellerCases({ token, kind, id }: { token: string; kind: string; id: number }) {
  const [reason, setReason] = useState("");
  const [rows, setRows] = useState<{ id: number; kind: string; status: string; resolution: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const path = `/partners/seller/${kind}/orders/${id}/cases/`;
  const refresh = async () => { setRows(await request<typeof rows>(path, {}, token)); };
  useEffect(() => { refresh().catch(e => setError(e.message)); }, [path, token]);
  return <View style={{ gap: 10 }}><Text style={{ fontWeight: "700" }}>Cancellation, refund & dispute requests</Text><Text>Requests are reviewed by operations. Only this seller’s items are included.</Text>
    {rows.map(row => <Text key={row.id}>#{row.id} · {row.kind}: {row.status}{row.resolution ? ` · ${row.resolution}` : ""}</Text>)}
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
    <TextInput accessibilityLabel="Reason for seller request" multiline value={reason} onChangeText={setReason} maxLength={1000} placeholder="Explain the issue" style={{ borderWidth: 1, padding: 12, minHeight: 60 }} />
    {(["cancellation", "refund", "dispute"] as const).map(action => <Pressable key={action} accessibilityRole="button" disabled={busy || reason.trim().length < 5} style={{ paddingVertical: 12 }} onPress={async () => {
      setBusy(true); setError(""); try { await request(path, { method: "POST", body: JSON.stringify({ kind: action, reason }) }, token); setReason(""); await refresh(); } catch (e: any) { setError(e.message); } finally { setBusy(false); }
    }}><Text>Request {action} review</Text></Pressable>)}
  </View>;
}

export function RiderEvidence({ token, id }: { token: string; id: number }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [choosingReason, setChoosingReason] = useState(false);
  const [pendingPhoto, setPendingPhoto] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const send = async (reason?: string) => {
    if (busy) return;
    setBusy(true); setMessage("");
    try {
      const form = new FormData();
      if (reason) form.append("reason", reason);
      else {
        let asset = pendingPhoto;
        if (!asset) {
          const permission = await ImagePicker.requestCameraPermissionsAsync();
          if (!permission.granted) throw new Error("Camera permission is required for delivery evidence.");
          const image = await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], quality: 0.65 });
          if (image.canceled) return;
          asset = image.assets[0]; setPendingPhoto(asset);
        }
        appendPhoto(form, "photo", asset);
      }
      await request(`/partners/rider/jobs/${id}/evidence/`, { method: "POST", body: form }, token);
      setChoosingReason(false);
      if (!reason) setPendingPhoto(null);
      setMessage(reason ? "Failure reported. Contact dispatch for the next step." : "Delivery photo saved.");
    } catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  };
  return <View><Pressable accessibilityRole="button" disabled={busy} style={{ paddingVertical: 14 }} onPress={() => send()}><Text>{pendingPhoto ? "Retry photo upload" : "Take proof-of-delivery photo"}</Text></Pressable>
    {pendingPhoto && <Pressable accessibilityRole="button" disabled={busy} style={{ paddingVertical: 14 }} onPress={() => setPendingPhoto(null)}><Text>Discard photo</Text></Pressable>}
    <Pressable accessibilityRole="button" disabled={busy} style={{ paddingVertical: 14 }} onPress={() => setChoosingReason(value => !value)}><Text>{choosingReason ? "Close reasons" : "Report delivery problem"}</Text></Pressable>
    {choosingReason && <View><Text>Choose a reason. This does not complete or cancel the job.</Text>{["customer_unavailable", "incorrect_address", "customer_refused", "unsafe_location", "vehicle_breakdown"].map(reason => <Pressable key={reason} accessibilityRole="button" disabled={busy} style={{ paddingVertical: 14 }} onPress={() => send(reason)}><Text>{reason.replace(/_/g, " ")}</Text></Pressable>)}</View>}
    {!!message && <Text accessibilityRole="alert">{message}</Text>}</View>;
}
