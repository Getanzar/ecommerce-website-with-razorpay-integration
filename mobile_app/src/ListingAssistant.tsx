import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Image, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import type { ImagePickerAsset } from "expo-image-picker";
import { request } from "./api";
import { appendPhoto } from "./uploads";

type Proposal = {
  draft: { name: string; description: string; brand: string; unit: string; colours: string[]; keywords: string[]; review_notes: string[] };
  fields: Record<string, string>; remaining_today: number; suggested_category?: string | null;
};
type Props = { token: string; kind: string; images: Record<string, ImagePickerAsset>; disabled: boolean; onPick: () => void; onApply: (fields: Record<string, string>) => void; onBusy: (busy: boolean) => void };

export default function ListingAssistant({ token, kind, images, disabled, onPick, onApply, onBusy }: Props) {
  const [notes, setNotes] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const photoKey = `${images.image?.uri || ""}:${images.back_image?.uri || ""}`;
  useEffect(() => { generation.current++; setProposal(null); setError(""); }, [photoKey, notes, kind, token]);
  useEffect(() => () => { generation.current++; }, []);
  const generate = async () => {
    if (busy || disabled) return;
    const photos = [images.image, images.back_image].filter(Boolean);
    if (!photos.length) { setError("Choose a product photo first. Existing saved photos must be selected again to generate a draft."); return; }
    const current = ++generation.current;
    setBusy(true); onBusy(true); setError(""); setProposal(null);
    try {
      const body = new FormData();
      body.append("kind", kind); body.append("notes", notes.trim());
      photos.forEach(photo => appendPhoto(body, "photos", photo));
      const result = await request<Proposal>("/partners/seller/listing-assistant/", { method: "POST", body }, token);
      if (current === generation.current) setProposal(result);
    } catch (error) {
      if (current === generation.current) setError(error instanceof Error ? error.message : "Could not generate a draft. You can still complete the form manually.");
    } finally { setBusy(false); onBusy(false); }
  };
  return <View style={s.panel}>
    <Text style={s.eyebrow}>LESS TYPING. MORE SELLING.</Text>
    <Text style={s.title}>AI listing assistant</Text>
    <Text style={s.copy}>Turn product photos and a short note into an editable draft. Photos and notes are sent to Google Gemini when you generate.</Text>
    {images.image && <Image source={{ uri: images.image.uri }} style={s.photo} />}
    <Pressable accessibilityRole="button" disabled={disabled || busy} style={s.secondary} onPress={onPick}><Text style={s.link}>{images.image ? "Change product photo" : "Choose product photo"}</Text></Pressable>
    <TextInput accessibilityLabel="AI listing seller notes" editable={!busy && !disabled} value={notes} onChangeText={setNotes} maxLength={2000} multiline placeholder="Optional: product type, confirmed material, brand or pack size" placeholderTextColor="#66746A" style={s.input} />
    <Pressable accessibilityRole="button" disabled={disabled || busy} style={[s.button, (disabled || busy) && s.disabled]} onPress={() => void generate()}>{busy ? <ActivityIndicator color="white" /> : <Text style={s.buttonText}>Generate listing draft</Text>}</Pressable>
    {busy && <Text accessibilityLiveRegion="polite" style={s.copy}>Reading photos and preparing your draft…</Text>}
    {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
    {proposal && <View style={s.result}>
      <Text style={s.title}>{proposal.draft.name}</Text>
      {!!proposal.draft.description && <Text style={s.copy}>{proposal.draft.description}</Text>}
      {!!proposal.suggested_category && <Text style={s.copy}>{kind === "food" ? "Menu section" : "Category"}: {proposal.suggested_category}</Text>}
      {!!proposal.draft.brand && <Text style={s.copy}>Brand: {proposal.draft.brand}</Text>}
      {!!proposal.draft.unit && <Text style={s.copy}>Pack size: {proposal.draft.unit}</Text>}
      {!!proposal.draft.colours.length && <Text style={s.copy}>Colours: {proposal.draft.colours.join(", ")}</Text>}
      {!!proposal.draft.keywords.length && <Text style={s.copy}>Keywords: {proposal.draft.keywords.join(", ")}</Text>}
      {proposal.draft.review_notes.map((note, index) => <Text key={index} style={s.copy}>• {note}</Text>)}
      <Text style={s.copy}>Review the draft. Confirm price, stock, sizes and product facts yourself. Applying it does not save or publish your listing.</Text>
      <Text style={s.copy}>{proposal.remaining_today} generations remaining today.</Text>
      <Pressable accessibilityRole="button" style={s.button} onPress={() => Alert.alert("Apply listing draft?", "This replaces the suggested text and category fields. Your prices, stock and photos are kept.", [{ text: "Cancel", style: "cancel" }, { text: "Apply draft", onPress: () => { onApply(proposal.fields); setProposal(null); } }])}><Text style={s.buttonText}>Apply draft to form</Text></Pressable>
      <Pressable accessibilityRole="button" style={s.secondary} onPress={() => setProposal(null)}><Text style={s.link}>Discard draft</Text></Pressable>
    </View>}
  </View>;
}

const s = StyleSheet.create({
  panel: { backgroundColor: "#F2F7EE", borderWidth: 1, borderColor: "#D9E6D3", padding: 16, borderRadius: 16, gap: 12, marginBottom: 20 },
  eyebrow: { fontSize: 10, fontWeight: "700", letterSpacing: 1.2, color: "#17634A" },
  title: { fontSize: 19, lineHeight: 25, fontWeight: "700", color: "#182B20" },
  copy: { fontSize: 13, lineHeight: 20, color: "#526658" },
  photo: { width: 80, height: 80, resizeMode: "contain", borderRadius: 10, backgroundColor: "white" },
  secondary: { minHeight: 44, justifyContent: "center", alignItems: "center", borderWidth: 1, borderColor: "#BDCFBC", borderRadius: 10, padding: 10 },
  link: { color: "#17634A", fontWeight: "700", fontSize: 13 },
  input: { minHeight: 88, textAlignVertical: "top", borderWidth: 1, borderColor: "#D9E6D3", borderRadius: 10, backgroundColor: "white", color: "#182B20", padding: 12, fontSize: 14 },
  button: { backgroundColor: "#17634A", minHeight: 48, alignItems: "center", justifyContent: "center", borderRadius: 10, padding: 12 },
  buttonText: { color: "white", fontWeight: "700", fontSize: 13 },
  disabled: { opacity: 0.5 },
  error: { fontSize: 13, lineHeight: 20, color: "#B42318" },
  result: { gap: 12, paddingTop: 16, borderTopWidth: 1, borderTopColor: "#D9E6D3" },
});
