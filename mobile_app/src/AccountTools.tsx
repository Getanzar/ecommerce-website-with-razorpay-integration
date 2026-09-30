import { appendPhoto } from "./uploads";
import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Image, Modal, Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import { changePassword, createSupportTicket, getNotificationPreferences, getSupportTickets, replySupportTicket, request, requestAccountDeletion, updateNotificationPreferences } from "./api";

type Ticket = { id: number; reason: string; message: string; status: string; request_type: string; order_id: number | null; attachment_url: string | null; replies: { id: number; message: string; is_staff: boolean; attachment_url: string | null }[] };
type Preferences = { order_updates: boolean; payment_updates: boolean; promotions: boolean };

export default function AccountTools({ token, mode, onClose, onSignedOut }: { token: string; mode: "support" | "settings"; onClose: () => void; onSignedOut: () => void }) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [deletion, setDeletion] = useState<string | null>(null);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [image, setImage] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [deletionReason, setDeletionReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [sessions, setSessions] = useState<{ id: number; device_name: string; last_seen_at: string; current: boolean }[]>([]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const load = async () => {
      if (mode === "support") {
        const rows = await getSupportTickets(token);
        if (!cancelled) setTickets(rows);
      } else {
        const [prefs, status] = await Promise.all([getNotificationPreferences(token), request<{ status: string | null }>("/account/delete-request/", {}, token)]);
        const devices = await request<typeof sessions>("/account/sessions/", {}, token);
        if (!cancelled) { setPreferences(prefs); setDeletion(status.status); setSessions(devices); }
      }
    };
    load().catch(err => { if (!cancelled) setError(err.message); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [mode, refresh, token]);

  const perform = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true); setError("");
    try { await fn(); }
    catch (err) { setError(err instanceof Error ? err.message : "Please try again."); }
    finally { setBusy(false); }
  };
  const pickImage = () => perform(async () => {
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.7 });
    if (!result.canceled) {
      if ((result.assets[0].fileSize || 0) > 8 * 1024 * 1024) throw new Error("Choose an image smaller than 8 MB.");
      setImage(result.assets[0]);
    }
  });
  const send = () => perform(async () => {
    const form = new FormData();
    form.append("message", message);
    if (image) appendPhoto(form, "attachment", image);
    if (selected) await replySupportTicket(token, selected, form);
    else { form.append("reason", subject); await createSupportTicket(token, form); }
    setSubject(""); setMessage(""); setImage(null); setRefresh(n => n + 1);
  });
  const ticket = tickets.find(row => row.id === selected);

  return (
    <Modal visible animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={s.screen}>
        <View style={s.header}>
          <Text style={s.heading}>{mode === "support" ? "Help & support" : "Account settings"}</Text>
          <Pressable onPress={onClose}><Text style={s.link}>Close</Text></Pressable>
        </View>
        <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled" refreshControl={<RefreshControl refreshing={loading} onRefresh={() => setRefresh(n => n + 1)} />}>
          {loading && <ActivityIndicator color="#C84E1F" />}
          {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
          {mode === "support" ? (
            <>
              <Text style={s.note}>Read replies from the support team or start a new conversation. For item returns, open the order and choose “Return this item”.</Text>
              {selected ? <Pressable onPress={() => { setSelected(null); setMessage(""); setImage(null); }}><Text style={s.link}>← All conversations / new request</Text></Pressable> : tickets.map(row => (
                <Pressable key={row.id} style={s.card} onPress={() => { setSelected(row.id); setMessage(""); setImage(null); }}>
                  <Text style={s.title}>#{row.id} · {row.reason}</Text>
                  <Text style={s.note}>{row.status}{row.order_id ? ` · Order #${row.order_id}` : ""} · {row.replies.length} replies</Text>
                </Pressable>
              ))}
              {!loading && tickets.length === 0 && <Text style={s.note}>No conversations yet.</Text>}
              {ticket && <View style={s.card}>
                <Text style={s.title}>{ticket.reason} · {ticket.status}</Text>
                <Text style={s.body}>{ticket.message}</Text>
                {ticket.attachment_url && <Image source={{ uri: ticket.attachment_url }} style={s.photo} />}
                {ticket.replies.map(reply => <View key={reply.id} style={s.reply}>
                  <Text style={s.title}>{reply.is_staff ? "Support team" : "You"}</Text>
                  <Text style={s.body}>{reply.message}</Text>
                  {reply.attachment_url && <Image source={{ uri: reply.attachment_url }} style={s.photo} />}
                </View>)}
              </View>}
              <View style={s.card}>
                <Text style={s.title}>{selected ? "Reply" : "New support request"}</Text>
                {!selected && <TextInput style={s.input} accessibilityLabel="Support subject" placeholder="Subject" maxLength={100} value={subject} onChangeText={setSubject} />}
                <TextInput style={[s.input, s.multiline]} accessibilityLabel="Support message" placeholder="Describe the issue" multiline maxLength={5000} value={message} onChangeText={setMessage} />
                <Pressable disabled={busy} onPress={pickImage}><Text style={s.link}>{image ? "Change attachment" : "Attach a photo"}</Text></Pressable>
                {image && <Image source={{ uri: image.uri }} style={s.photo} />}
                <Pressable disabled={busy || message.trim().length < 5 || (!selected && subject.trim().length < 3)} style={s.button} onPress={send}><Text style={s.buttonText}>{busy ? "Sending…" : "Send"}</Text></Pressable>
              </View>
            </>
          ) : (
            <>
              {preferences && <View style={s.card}>
                <Text style={s.title}>Notification preferences</Text>
                {(["order_updates", "payment_updates", "promotions"] as const).map(key => <View key={key} style={s.row}>
                  <Text style={s.body}>{key.replace(/_/g, " ")}</Text>
                  <Switch accessibilityLabel={key.replace(/_/g, " ")} disabled={busy} value={preferences[key]} onValueChange={value => perform(async () => { setPreferences(await updateNotificationPreferences(token, { ...preferences, [key]: value })); })} />
                </View>)}
              </View>}
              <View style={s.card}>
                <Text style={s.title}>Devices & sessions</Text>
                {sessions.map(session => <View key={session.id}><Text style={s.body}>{session.device_name}{session.current ? " · This device" : ""}</Text><Text style={s.note}>Last active: {new Date(session.last_seen_at).toLocaleString()}</Text><Pressable accessibilityRole="button" disabled={busy} style={{ minHeight: 44, justifyContent: "center" }} onPress={() => perform(async () => { await request(`/account/sessions/${session.id}/`, { method: "DELETE" }, token); if (session.current) onSignedOut(); else setRefresh(n => n + 1); })}><Text style={s.error}>Revoke session</Text></Pressable></View>)}
              </View>
              <View style={s.card}>
                <Text style={s.title}>Change password</Text>
                <Text style={s.note}>Changing your password signs you out of mobile sessions.</Text>
                <TextInput style={s.input} accessibilityLabel="Current password" placeholder="Current password" secureTextEntry value={currentPassword} onChangeText={setCurrentPassword} />
                <TextInput style={s.input} accessibilityLabel="New password" placeholder="New password" secureTextEntry value={newPassword} onChangeText={setNewPassword} />
                <TextInput style={s.input} accessibilityLabel="Confirm new password" placeholder="Confirm new password" secureTextEntry value={confirmPassword} onChangeText={setConfirmPassword} />
                <Pressable style={s.button} disabled={busy || !currentPassword || newPassword.length < 8 || newPassword !== confirmPassword} onPress={() => perform(async () => {
                  await changePassword(token, currentPassword, newPassword);
                  Alert.alert("Password changed", "Sign in again with your new password."); onSignedOut();
                })}><Text style={s.buttonText}>{busy ? "Please wait…" : "Change password"}</Text></Pressable>
              </View>
              <View style={s.card}>
                <Text style={s.title}>Account deletion request</Text>
                <Text style={s.note}>Submitting a request signs you out. Account data is not immediately erased; the marketplace team processes the request.</Text>
                {deletion && <Text style={s.body}>Request status: {deletion}</Text>}
                {!deletion && <>
                  <TextInput style={s.input} accessibilityLabel="Deletion reason" placeholder="Reason (optional)" maxLength={300} value={deletionReason} onChangeText={setDeletionReason} />
                  <Pressable disabled={busy} onPress={() => Alert.alert("Request account deletion?", "This sends a deletion request and signs you out of mobile sessions.", [
                    { text: "Keep account", style: "cancel" },
                    { text: "Submit request", style: "destructive", onPress: () => perform(async () => { await requestAccountDeletion(token, deletionReason); onSignedOut(); }) },
                  ])}><Text style={s.error}>Request deletion</Text></Pressable>
                </>}
              </View>
            </>
          )}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#FFF8EF" }, header: { padding: 20, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, heading: { fontSize: 22, fontWeight: "800", color: "#17243A" },
  content: { padding: 20, gap: 16, paddingBottom: 45 }, card: { padding: 16, borderWidth: 1, borderColor: "#E4DDD4", borderRadius: 14, backgroundColor: "white", gap: 12 }, title: { color: "#17243A", fontWeight: "700", fontSize: 16 },
  note: { color: "#5D6B7D", lineHeight: 21 }, body: { color: "#17243A", lineHeight: 22 }, row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, reply: { borderTopWidth: 1, borderColor: "#ECE7DF", paddingTop: 12, gap: 8 },
  input: { padding: 12, borderWidth: 1, borderColor: "#BDC7D1", borderRadius: 10, color: "#17243A" }, multiline: { minHeight: 100, textAlignVertical: "top" }, link: { color: "#A83D16", fontWeight: "700", paddingVertical: 9 }, error: { color: "#AF2424", lineHeight: 22 },
  button: { backgroundColor: "#C84E1F", padding: 15, borderRadius: 12, alignItems: "center" }, buttonText: { color: "white", fontWeight: "700" }, photo: { height: 160, width: 160, borderRadius: 10 },
});
