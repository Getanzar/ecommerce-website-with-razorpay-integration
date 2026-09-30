import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Image, Modal, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import * as Location from "expo-location";
import { request } from "./api";
import { appendPhoto } from "./uploads";
import ProductVariantsForm, { emptyVariant, NewVariant, validateVariants } from "./ProductVariantsForm";
import {
  partnerRequest,
  SellerCategory,
  SellerCategoriesResponse,
} from "./partnerApi";

type Field = { name: string; label: string; required: boolean; type: string; value: string; choices: string[][]; help: string };
export default function PartnerForm({ token, path, title, onClose, onSaved }: { token: string; path: string; title: string; onClose: () => void; onSaved: () => void }) {
  const [fields, setFields] = useState<Field[]>([]);
  const [sellerCategories, setSellerCategories] = useState<SellerCategory[]>([]);
  const [showAddCategory, setShowAddCategory] = useState(false);
const [showAddSubcategory, setShowAddSubcategory] = useState(false);
const [newCategoryName, setNewCategoryName] = useState("");
const [newSubcategoryName, setNewSubcategoryName] = useState("");
const [taxonomyBusy, setTaxonomyBusy] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [images, setImages] = useState<Record<string, ImagePicker.ImagePickerAsset>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [variants, setVariants] = useState<NewVariant[]>([emptyVariant()]);
  const [uploadStage, setUploadStage] = useState("");
  const submitting = useRef(false);
  const scroll = useRef<ScrollView>(null);
  const isNewMerchandise = path === "seller/products/new/";
  const isMerchandiseProductForm =
  path === "seller/products/new/" ||
  /^seller\/products\/\d+\/edit\/$/.test(path);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError("");
    partnerRequest<{ fields: Field[] }>(token, path).then(data => {
      if (!cancelled) { setFields(data.fields); setValues(Object.fromEntries(data.fields.map(f => [f.name, f.value]))); }
    }).catch(err => { if (!cancelled) setError(err.message); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [path, token, retry]);
  useEffect(() => {
  let cancelled = false;

  // Only merchandise products use the shared Category/Subcategory taxonomy.
  if (path !== "seller/products/new/" && !path.match(/^seller\/products\/\d+\/edit\/$/)) {
    setSellerCategories([]);
    return;
  }

  partnerRequest<SellerCategoriesResponse>(
    token,
    "seller/categories/"
  )
    .then(data => {
      if (!cancelled) {
        setSellerCategories(data.categories);
      }
    })
    .catch(err => {
      if (!cancelled) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load product categories."
        );
      }
    });

  return () => {
    cancelled = true;
  };
}, [path, token, retry]);
  const change = (name: string, value: string) => setValues(prev => ({ ...prev, [name]: value }));
  const selectedCategory = sellerCategories.find(
  category => String(category.id) === values.category
);

const availableSubcategories = selectedCategory?.subcategories ?? [];

const selectCategory = (categoryId: string) => {
  setValues(prev => ({
    ...prev,
    category: categoryId,
    subcategory: "",
  }));
};

const createCategory = async () => {
  const name = newCategoryName.trim();

  if (!name) {
    setError("Enter a category name.");
    return;
  }

  if (taxonomyBusy) return;

  setTaxonomyBusy(true);
  setError("");

  try {
    const result = await partnerRequest<{
      message: string;
      id: number;
      name: string;
      slug?: string;
      type: string;
    }>(
      token,
      "seller/categories/",
      "POST",
      { name }
    );

    // Reload the complete taxonomy after creation.
    const taxonomy = await partnerRequest<SellerCategoriesResponse>(
      token,
      "seller/categories/"
    );

    setSellerCategories(taxonomy.categories);

    // Automatically select the newly created/existing category.
    setValues(prev => ({
      ...prev,
      category: String(result.id),
      subcategory: "",
    }));

    setNewCategoryName("");
    setShowAddCategory(false);
  } catch (err) {
    setError(
      err instanceof Error
        ? err.message
        : "Unable to create category."
    );
  } finally {
    setTaxonomyBusy(false);
  }
};

const createSubcategory = async () => {
  const name = newSubcategoryName.trim();

  if (!values.category) {
    setError("Select a category first.");
    return;
  }

  if (!name) {
    setError("Enter a subcategory name.");
    return;
  }

  if (taxonomyBusy) return;

  setTaxonomyBusy(true);
  setError("");

  try {
    const result = await partnerRequest<{
      message: string;
      id: number;
      name: string;
      category_id: number;
      type: string;
    }>(
      token,
      "seller/categories/",
      "POST",
      {
        name,
        parent_category: Number(values.category),
      }
    );

    // Reload Category -> Subcategory hierarchy.
    const taxonomy = await partnerRequest<SellerCategoriesResponse>(
      token,
      "seller/categories/"
    );

    setSellerCategories(taxonomy.categories);

    // Automatically select the newly created/existing subcategory.
    setValues(prev => ({
      ...prev,
      subcategory: String(result.id),
    }));

    setNewSubcategoryName("");
    setShowAddSubcategory(false);
  } catch (err) {
    setError(
      err instanceof Error
        ? err.message
        : "Unable to create subcategory."
    );
  } finally {
    setTaxonomyBusy(false);
  }
};

  const pick = async (name: string) => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.7, preferredAssetRepresentationMode: ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Compatible });
      if (!result.canceled) {
        if ((result.assets[0].fileSize || 0) > 8 * 1024 * 1024) throw new Error("Choose an image smaller than 8 MB.");
        setImages(prev => ({ ...prev, [name]: result.assets[0] }));
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to select image."); }
  };
  const capture = async () => {
    setBusy(true); setError("");
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) throw new Error("Location permission is needed to capture your business address.");
      const location = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      if (location.coords.accuracy === null || location.coords.accuracy > 500) throw new Error("Move outdoors and retry for better GPS accuracy.");
      setValues(prev => ({ ...prev, [fields.some(f => f.name === "business_latitude") ? "business_latitude" : "latitude"]: location.coords.latitude.toFixed(6), [fields.some(f => f.name === "business_longitude") ? "business_longitude" : "longitude"]: location.coords.longitude.toFixed(6), [fields.some(f => f.name === "business_gps_accuracy_meters") ? "business_gps_accuracy_meters" : "gps_accuracy_meters"]: String(Math.round(location.coords.accuracy!)), gps_captured_at: new Date(location.timestamp).toISOString() }));
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to capture location."); } finally { setBusy(false); }
  };
  const submit = async () => {
    if (busy || submitting.current) return;
    submitting.current = true;
    setBusy(true); setError("");
    try {
      for (const field of fields) {
        if (!field.required || (isNewMerchandise && ["color_name", "size", "opening_stock", "variants"].includes(field.name))) continue;
        if (field.type === "image" ? !images[field.name] : !(values[field.name] || "").trim()) throw new Error(`${field.label} is required.`);
      }
      if (isNewMerchandise) {
        const validation = validateVariants(variants);
        if (validation) throw new Error(validation);
      }
      setUploadStage("Checking connectionâ€¦");
      // Read-only check distinguishes a disconnected preview from a photo upload failure.
      await partnerRequest(token, path);
      const data = new FormData();
      for (const field of fields) {
        if (isNewMerchandise && ["color_name", "size", "opening_stock", "variants"].includes(field.name)) continue;
        if (field.type === "image") {
          const image = images[field.name];
          if (image) appendPhoto(data, field.name, image);
        } else if (field.type === "multiple") { for (const value of (values[field.name] || "").split(",").filter(Boolean)) data.append(field.name, value); } else data.append(field.name, values[field.name] || "");
      }
      if (isNewMerchandise) data.append("variants", JSON.stringify(variants.map(row => ({ color: row.color.trim(), size: row.size.trim(), stock: Number(row.stock) }))));
      setUploadStage("Uploading and savingâ€¦ Keep this screen open.");
      const result = await request<{ message: string }>(`/partners/${path}`, { method: "POST", body: data }, token);
      Alert.alert("Saved", result.message); onSaved();
    } catch (err) { const message = err instanceof Error ? err.message : "Unable to save."; setError(message); Alert.alert("Save not confirmed", message); } finally { setBusy(false); setUploadStage(""); submitting.current = false; }
  };
  return <Modal visible animationType="slide" onRequestClose={onClose}><SafeAreaView style={s.screen}><View style={s.header}><Text style={s.title}>{title}</Text><Pressable disabled={busy} onPress={onClose} accessibilityRole="button"><Text style={s.link}>Close</Text></Pressable></View><ScrollView ref={scroll} contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">{loading && <ActivityIndicator />}{!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
  {!loading && fields.length === 0 &&
  <Pressable style={s.button} onPress={() => setRetry(n => n + 1)}>
    <Text style={s.buttonText}>Retry</Text>
  </Pressable>}
  {!loading && isMerchandiseProductForm && (
  <View style={s.field}>
    <Text style={s.label}>Category *</Text>

    <View style={s.choices}>
      {sellerCategories.map(category => (
        <Pressable
          key={category.id}
          disabled={busy}
          accessibilityRole="radio"
          accessibilityState={{
            checked: values.category === String(category.id),
          }}
          onPress={() => selectCategory(String(category.id))}
          style={[
            s.choice,
            values.category === String(category.id) && s.selected,
          ]}
        >
          <Text>{category.name}</Text>
        </Pressable>
      ))}
    </View>

    {sellerCategories.length === 0 && (
  <Text style={s.help}>No categories available yet.</Text>
)}

<Pressable
  disabled={busy || taxonomyBusy}
  onPress={() => setShowAddCategory(prev => !prev)}
  style={s.taxonomyLink}
>
  <Text style={s.taxonomyLinkText}>
    {showAddCategory ? "Cancel" : "+ Add new category"}
  </Text>
</Pressable>

{showAddCategory && (
  <View style={s.taxonomyCreate}>
    <TextInput
      placeholder="e.g. Electronics"
      value={newCategoryName}
      onChangeText={setNewCategoryName}
      editable={!taxonomyBusy}
      style={s.input}
      autoCapitalize="words"
    />

    <Pressable
      disabled={taxonomyBusy}
      onPress={createCategory}
      style={[
        s.button,
        taxonomyBusy && { opacity: 0.5 },
      ]}
    >
      <Text style={s.buttonText}>
        {taxonomyBusy ? "Creating..." : "Create category"}
      </Text>
    </Pressable>
  </View>
)}
  </View>
)}
{!loading && isMerchandiseProductForm && values.category && (
  <View style={s.field}>
    <Text style={s.label}>Subcategory</Text>

    {availableSubcategories.length > 0 ? (
      <View style={s.choices}>
        {availableSubcategories.map(subcategory => (
          <Pressable
            key={subcategory.id}
            disabled={busy}
            accessibilityRole="radio"
            accessibilityState={{
              checked: values.subcategory === String(subcategory.id),
            }}
            onPress={() =>
              change("subcategory", String(subcategory.id))
            }
            style={[
              s.choice,
              values.subcategory === String(subcategory.id) && s.selected,
            ]}
          >
            <Text>{subcategory.name}</Text>
          </Pressable>
        ))}
      </View>
    ) : (
      <Text style={s.help}>
        No subcategories have been added to this category yet.
      </Text>
    )}
    <Pressable
  disabled={busy || taxonomyBusy}
  onPress={() => setShowAddSubcategory(prev => !prev)}
  style={s.taxonomyLink}
>
  <Text style={s.taxonomyLinkText}>
    {showAddSubcategory ? "Cancel" : "+ Add new subcategory"}
  </Text>
</Pressable>

{showAddSubcategory && (
  <View style={s.taxonomyCreate}>
    <TextInput
      placeholder={
        selectedCategory
          ? `Add under ${selectedCategory.name}`
          : "Subcategory name"
      }
      value={newSubcategoryName}
      onChangeText={setNewSubcategoryName}
      editable={!taxonomyBusy}
      style={s.input}
      autoCapitalize="words"
    />

    <Pressable
      disabled={taxonomyBusy}
      onPress={createSubcategory}
      style={[
        s.button,
        taxonomyBusy && { opacity: 0.5 },
      ]}
    >
      <Text style={s.buttonText}>
        {taxonomyBusy ? "Creating..." : "Create subcategory"}
      </Text>
    </Pressable>
  </View>
)}
  </View>
)}
  {fields.filter(f => {
    if (f.type === "hidden") return false;
    if (isNewMerchandise && ["color_name", "size", "opening_stock"].includes(f.name)) return false;

    if (
      isMerchandiseProductForm &&
      (f.name === "category" || f.name === "subcategory")
    ) {
      return false;
    }

    return true;
  })
  .map(field => <View key={field.name} style={s.field}><Text style={s.label}>{field.label}{field.required ? " *" : ""}</Text>{(field.type === "choice" || field.type === "multiple") ? <View style={s.choices}>{field.choices.map(([value, title]) => <Pressable key={value} disabled={busy} accessibilityRole="radio" accessibilityState={{ checked: (field.type === "multiple" ? (values[field.name] || "").split(",").includes(value) : values[field.name] === value) }} onPress={() => { if (field.type === "multiple") { const selected = (values[field.name] || "").split(",").filter(Boolean); change(field.name, selected.includes(value) ? selected.filter(v => v !== value).join(",") : [...selected, value].join(",")); } else change(field.name, value); }} style={[s.choice, (field.type === "multiple" ? (values[field.name] || "").split(",").includes(value) : values[field.name] === value) && s.selected]}><Text>{title}</Text></Pressable>)}</View> : field.type === "boolean" ? <Switch accessibilityLabel={field.label} disabled={busy} value={values[field.name] === "True"} onValueChange={v => change(field.name, v ? "True" : "")} /> : field.type === "image" ? <Pressable accessibilityRole="button" disabled={busy} style={s.choice} onPress={() => pick(field.name)}><Text>{images[field.name] ? "Image selected Â· Change" : "Choose image"}</Text>{images[field.name] && <Image source={{ uri: images[field.name].uri }} style={{ width: 100, height: 100, marginTop: 8, borderRadius: 8 }} resizeMode="contain" />}</Pressable> : <TextInput accessibilityLabel={field.label} editable={!busy} style={[s.input, field.type === "multiline" && { minHeight: 100 }]} value={values[field.name] || ""} onChangeText={value => change(field.name, value)} multiline={field.type === "multiline"} secureTextEntry={field.type === "password"} keyboardType={field.type === "number" ? "decimal-pad" : "default"} autoCapitalize="none" />}{!!field.help && <Text style={s.help}>{field.help.replace(/<[^>]*>/g, "")}</Text>}</View>)}{isNewMerchandise && !loading && fields.length > 0 && <ProductVariantsForm rows={variants} onChange={setVariants} disabled={busy} />}{fields.some(f => f.name === "gps_captured_at") && <View style={s.field}><Text style={s.help}>Capture GPS while you are at your business address. It expires after five minutes.</Text><Pressable disabled={busy} style={s.choice} onPress={capture}><Text>{values.gps_captured_at ? "GPS captured Â· Capture again" : "Capture business location"}</Text></Pressable></View>}{!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}{!!uploadStage && <Text accessibilityLiveRegion="polite" style={s.help}>{uploadStage}</Text>}{fields.length > 0 && <Pressable accessibilityRole="button" disabled={busy || loading} style={[s.button, busy && { opacity: 0.5 }]} onPress={submit}><Text style={s.buttonText}>{busy ? "Please waitâ€¦" : isNewMerchandise ? "Submit product for review" : "Submit"}</Text></Pressable>}</ScrollView></SafeAreaView></Modal>;
}
const s = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#FFF8EF",
  },

  header: {
    padding: 20,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
  },

  title: {
    fontSize: 21,
    fontWeight: "800",
    color: "#17243A",
    flexShrink: 1,
  },

  link: {
    color: "#AA4119",
    fontWeight: "700",
    padding: 10,
  },

  content: {
    padding: 20,
    gap: 20,
    paddingBottom: 50,
  },

  field: {
    gap: 8,
  },

  label: {
    fontWeight: "700",
    color: "#17243A",
  },

  input: {
    borderWidth: 1,
    borderColor: "#C7CFD8",
    borderRadius: 10,
    padding: 13,
    backgroundColor: "white",
    color: "#17243A",
  },

  help: {
    color: "#5D6B7D",
    lineHeight: 20,
  },

  choices: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },

  choice: {
    borderWidth: 1,
    borderColor: "#C7CFD8",
    padding: 13,
    borderRadius: 10,
    backgroundColor: "white",
  },

  selected: {
    borderColor: "#C84E1F",
    backgroundColor: "#FFE6D5",
  },

  taxonomyLink: {
    alignSelf: "flex-start",
    paddingVertical: 6,
  },

  taxonomyLinkText: {
    color: "#C84E1F",
    fontWeight: "800",
  },

  taxonomyCreate: {
    gap: 10,
    marginTop: 4,
  },

  button: {
    backgroundColor: "#C84E1F",
    padding: 16,
    borderRadius: 12,
    alignItems: "center",
  },

  buttonText: {
    color: "white",
    fontWeight: "800",
  },

  error: {
    color: "#B32929",
    lineHeight: 22,
  },
});
