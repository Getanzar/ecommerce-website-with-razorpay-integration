import React, { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { request } from "./api";

export type NotificationTarget = { kind?: string; order_id?: number; target?: string; delivery_id?: number };
type Entry = { id: number; title: string; body: string; data: NotificationTarget; read_at: string | null };

export default function NotificationInbox({ token, onOpen, onClose }: { token: string; onOpen: (data: NotificationTarget) => void; onClose: () => void }) {
  const [rows, setRows] = useState<Entry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [more, setMore] = useState(false);
  const load = async (append = false) => {
    setBusy(true); setError("");
    try {
      const result = await request<Entry[]>(`/notifications/${append && rows.length ? `?before=${rows[rows.length - 1].id}` : ""}`, {}, token);
      setRows(old => append ? [...old, ...result] : result); setMore(result.length === 50);
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  useEffect(() => { void load(); }, [token]);
  return <Modal onRequestClose={onClose}><SafeAreaView style={{ flex: 1, padding: 20, backgroundColor: "#FFF8EF" }}>
    <Text accessibilityRole="header" style={{ fontSize: 24, fontWeight: "700" }}>Notifications</Text>
    <Pressable accessibilityRole="button" onPress={onClose} style={{ paddingVertical: 16 }}><Text>Close</Text></Pressable>
    <ScrollView><Pressable accessibilityRole="button" disabled={busy} onPress={() => load()} style={{ paddingVertical: 16 }}><Text>Refresh</Text></Pressable>
      {!!error && <Text accessibilityRole="alert">{error}</Text>}{busy && <ActivityIndicator />}
      {!busy && !rows.length && <Text>No notifications yet.</Text>}
      {rows.map(row => <Pressable accessibilityRole="button" accessibilityLabel={`${row.read_at ? "" : "Unread. "}${row.title}. ${row.body}`} key={row.id} style={{ padding: 16, marginVertical: 6, backgroundColor: "white", borderRadius: 12 }} onPress={async () => {
        try { await request(`/notifications/${row.id}/`, { method: "PATCH" }, token); onOpen(row.data); } catch (e: any) { setError(e.message); }
      }}><Text style={{ fontWeight: row.read_at ? "400" : "700" }}>{row.title}</Text><Text>{row.body}</Text></Pressable>)}
      {more && <Pressable accessibilityRole="button" disabled={busy} onPress={() => load(true)} style={{ padding: 16 }}><Text>Load older notifications</Text></Pressable>}
    </ScrollView>
  </SafeAreaView></Modal>;
}
