import React from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

export type NewVariant = { color: string; size: string; stock: string };
export const emptyVariant = (): NewVariant => ({ color: "", size: "", stock: "" });
export function validateVariants(rows: NewVariant[]): string {
  if (!rows.length || rows.length > 100) return "Add between 1 and 100 variants.";
  const seen = new Set<string>();
  for (const [index, row] of rows.entries()) {
    if (!row.color.trim() || !row.size.trim()) return `Variant ${index + 1}: enter both color and size.`;
    if (!/^\d+$/.test(row.stock.trim()) || Number(row.stock) > 1000000) return `Variant ${index + 1}: stock must be a whole number between 0 and 1,000,000.`;
    const key = JSON.stringify([row.color.trim().toLowerCase(), row.size.trim().toLowerCase()]);
    if (seen.has(key)) return `Variant ${index + 1}: this color and size already exists. Update its stock instead.`;
    seen.add(key);
  }
  return "";
}

export default function ProductVariantsForm({ rows, onChange, disabled }: { rows: NewVariant[]; onChange: (rows: NewVariant[]) => void; disabled: boolean }) {
  const edit = (index: number, field: keyof NewVariant, value: string) => onChange(rows.map((row, i) => i === index ? { ...row, [field]: value } : row));
  return <View style={s.section}><Text style={s.title}>Colors, sizes & stock *</Text><Text style={s.help}>Add one variant for each color and size, for example Blue / M and Blue / L. All variants use the selling price above.</Text>
    {rows.map((row, index) => <View key={index} style={s.card}>
      <View style={s.line}><Text style={s.label}>Variant {index + 1}</Text>{rows.length > 1 && <Pressable accessibilityRole="button" accessibilityLabel={`Remove variant ${index + 1}`} disabled={disabled} onPress={() => onChange(rows.filter((_, i) => i !== index))} style={s.action}><Text style={s.link}>Remove</Text></Pressable>}</View>
      <Text style={s.label}>Color *</Text><TextInput accessibilityLabel={`Variant ${index + 1} color`} editable={!disabled} maxLength={50} style={s.input} placeholder="e.g. Blue, Black, Red" value={row.color} onChangeText={value => edit(index, "color", value)} />
      <Text style={s.label}>Size *</Text><TextInput accessibilityLabel={`Variant ${index + 1} size`} editable={!disabled} maxLength={30} style={s.input} placeholder="e.g. M, 32, 2–3 years, Free Size" value={row.size} onChangeText={value => edit(index, "size", value)} />
      <View style={s.sizes}>{["XS", "S", "M", "L", "XL", "XXL", "Free Size"].map(size => <Pressable key={size} accessibilityRole="radio" accessibilityState={{ checked: row.size === size }} disabled={disabled} onPress={() => edit(index, "size", size)} style={[s.chip, row.size === size && s.selected]}><Text>{size}</Text></Pressable>)}</View>
      <Text style={s.label}>Stock quantity *</Text><TextInput accessibilityLabel={`Variant ${index + 1} stock`} editable={!disabled} keyboardType="number-pad" maxLength={7} style={s.input} placeholder="e.g. 10" value={row.stock} onChangeText={value => edit(index, "stock", value)} />
    </View>)}
    <Pressable accessibilityRole="button" disabled={disabled || rows.length >= 100} style={s.add} onPress={() => onChange([...rows, { ...emptyVariant(), color: rows[rows.length - 1]?.color || "" }])}><Text style={s.link}>+ Add another color / size</Text></Pressable>
  </View>;
}
const s = StyleSheet.create({
  section: { gap: 12 }, title: { color: "#17243A", fontSize: 18, fontWeight: "800" }, help: { color: "#5D6B7D", lineHeight: 21 },
  card: { gap: 10, backgroundColor: "white", padding: 16, borderWidth: 1, borderColor: "#E9E2D8", borderRadius: 14 }, label: { color: "#17243A", fontWeight: "700" },
  line: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" }, input: { borderWidth: 1, borderColor: "#C7CFD8", padding: 13, borderRadius: 10, color: "#17243A" },
  sizes: { flexDirection: "row", flexWrap: "wrap", gap: 6 }, chip: { padding: 12, borderRadius: 8, backgroundColor: "#F2EDE5" }, selected: { backgroundColor: "#FFE6D5" },
  action: { padding: 12 }, link: { color: "#AA4119", fontWeight: "700" }, add: { padding: 16, borderWidth: 1, borderColor: "#C84E1F", borderRadius: 10, alignItems: "center" },
});
