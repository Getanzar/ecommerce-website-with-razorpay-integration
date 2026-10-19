import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Image, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import type { ImagePickerAsset } from "expo-image-picker";
import { request } from "./api";
import { File, Paths } from "expo-file-system";
import { appendPhoto } from "./uploads";

type Proposal = {
  catalogue_image?: { data: string; mime_type: string; name: string }; image_warning?: string;
  draft: { name: string; description: string; brand: string; unit: string; colours: string[]; keywords: string[]; review_notes: string[] };
  fields: Record<string, string>; remaining_today: number; suggested_category?: string | null;
};
type Props = { token: string; kind: string; images: Record<string, ImagePickerAsset>; disabled: boolean; onPick: () => void; onApply: (fields: Record<string, string>) => void; onBusy: (busy: boolean) => void; onApplyImage: (image: ImagePickerAsset) => void };

export default function ListingAssistant({ token, kind, images, disabled, onPick, onApply, onBusy, onApplyImage }: Props) {
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
      body.append("enhance_photo", "true"); body.append("kind", kind); body.append("notes", notes.trim());
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
    <Text style={s.copy}>Turn a raw photo into a professional catalogue photo, product name and description. Photos and notes are sent to Google Gemini when you generate.</Text>
    {images.image && <Image source={{ uri: images.image.uri }} style={s.photo} />}
    <Pressable accessibilityRole="button" disabled={disabled || busy} style={s.secondary} onPress={onPick}><Text style={s.link}>{images.image ? "Change product photo" : "Choose product photo"}</Text></Pressable>
    <TextInput accessibilityLabel="AI listing seller notes" editable={!busy && !disabled} value={notes} onChangeText={setNotes} maxLength={2000} multiline placeholder="Optional: product type, confirmed material, brand or pack size" placeholderTextColor="#66746A" style={s.input} />
    <Pressable accessibilityRole="button" disabled={disabled || busy} style={[s.button, (disabled || busy) && s.disabled]} onPress={() => void generate()}>{busy ? <ActivityIndicator color="white" /> : <Text style={s.buttonText}>Prepare catalogue photo and listing</Text>}</Pressable>
    {busy && <Text accessibilityLiveRegion="polite" style={s.copy}>Reading photos and preparing your draft…</Text>}
    {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
    {proposal && <View style={s.result}>
      {proposal.catalogue_image && <Image accessibilityLabel="Catalogue photo preview" source={{ uri: `data:${proposal.catalogue_image.mime_type};base64,${proposal.catalogue_image.data}` }} style={{ width: "100%", height: 260, resizeMode: "contain", backgroundColor: "white" }} />}
      {!!proposal.image_warning && <Text style={s.error}>{proposal.image_warning}</Text>}
      {proposal.catalogue_image && <Text style={s.copy}>Check colours, labels and product details. Applying replaces your main photo.</Text>}
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
      <Pressable accessibilityRole="button" style={s.button} onPress={() => Alert.alert("Apply listing draft?", "This replaces the suggested text and category fields. Review the text and photo. The catalogue photo replaces your main photo when available. Prices and stock are kept.", [{ text: "Cancel", style: "cancel" }, { text: "Apply draft", onPress: () => { try {
        if (proposal.catalogue_image) {
          const file = new File(Paths.cache, `catalogue-${Date.now()}.jpg`);
          file.write(Uint8Array.from(atob(proposal.catalogue_image.data), char => char.charCodeAt(0)));
          onApplyImage({ uri: file.uri, width: 1536, height: 1536, type: "image", mimeType: "image/jpeg", fileName: "catalogue-product.jpg" });
        }
        onApply(proposal.fields); setProposal(null);
      } catch { setError("Could not prepare the catalogue photo. Try again; your original photo is kept."); } } }])}><Text style={s.buttonText}>Apply draft to form</Text></Pressable>
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
