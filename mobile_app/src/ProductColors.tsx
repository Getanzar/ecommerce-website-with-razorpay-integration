import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { partnerRequest } from "./partnerApi";

type ProductColor = {
  id: number;
  name: string;
  hex_code: string;
  image: string | null;
};

type ProductColorsResponse = {
  colors: ProductColor[];
};

type Props = {
  token: string;
  productId: number;
  productName: string;
  onClose: () => void;
  onChanged: () => void;
};

export default function ProductColors({
  token,
  productId,
  productName,
  onClose,
  onChanged,
}: Props) {
  const [colors, setColors] = useState<ProductColor[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [name, setName] = useState("");
  const [hexCode, setHexCode] = useState("#000000");

  useEffect(() => {
  let cancelled = false;

  setLoading(true);
  setError("");

  partnerRequest<ProductColorsResponse>(
    token,
    `seller/products/${productId}/colors/`
  )
    .then(data => {
      if (!cancelled) {
        setColors(data.colors);
      }
    })
    .catch(err => {
      if (!cancelled) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load product colors."
        );
      }
    })
    .finally(() => {
      if (!cancelled) {
        setLoading(false);
      }
    });

  return () => {
    cancelled = true;
  };
}, [token, productId]);

const createColor = async () => {
  const colorName = name.trim();
  const colorHex = hexCode.trim();

  if (!colorName) {
    setError("Enter a color name.");
    return;
  }

  if (!/^#[0-9A-Fa-f]{6}$/.test(colorHex)) {
    setError("Enter a valid hex color, for example #000000.");
    return;
  }

  if (busy) return;

  setBusy(true);
  setError("");

  try {
    await partnerRequest(
      token,
      `seller/products/${productId}/colors/`,
      "POST",
      {
        name: colorName,
        hex_code: colorHex,
      }
    );

    // Reload colors after creating one.
    const data = await partnerRequest<ProductColorsResponse>(
      token,
      `seller/products/${productId}/colors/`
    );

    setColors(data.colors);

    setName("");
    setHexCode("#000000");

    onChanged();
  } catch (err) {
    setError(
      err instanceof Error
        ? err.message
        : "Unable to create color."
    );
  } finally {
    setBusy(false);
  }
};

  return (
  <Modal
    visible
    animationType="slide"
    onRequestClose={onClose}
  >
    <SafeAreaView style={s.screen}>
      <View style={s.header}>
        <View style={{ flex: 1 }}>
          <Text style={s.eyebrow}>PRODUCT COLORS</Text>
          <Text style={s.title}>{productName}</Text>
        </View>

        <Pressable
          onPress={onClose}
          style={s.secondaryButton}
        >
          <Text style={s.secondaryButtonText}>Close</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={s.content}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={s.sectionTitle}>Colors</Text>

        {loading && (
          <ActivityIndicator size="large" />
        )}

        {!!error && (
          <Text style={s.error}>{error}</Text>
        )}

        {!loading && colors.length === 0 && (
          <Text style={s.muted}>
            No colors have been added to this product yet.
          </Text>
        )}

        {colors.map(color => (
          <View key={color.id} style={s.colorCard}>
            <View
              style={[
                s.colorPreview,
                { backgroundColor: color.hex_code },
              ]}
            />

            <View style={{ flex: 1 }}>
              <Text style={s.colorName}>
                {color.name}
              </Text>

              <Text style={s.muted}>
                {color.hex_code}
              </Text>
            </View>
          </View>
        ))}

        <View style={s.divider} />

        <Text style={s.sectionTitle}>
          Add new color
        </Text>

        <Text style={s.label}>Color name</Text>

        <TextInput
          value={name}
          onChangeText={setName}
          placeholder="e.g. Black"
          editable={!busy}
          style={s.input}
          autoCapitalize="words"
        />

        <Text style={s.label}>Hex color</Text>

        <TextInput
          value={hexCode}
          onChangeText={setHexCode}
          placeholder="#000000"
          editable={!busy}
          style={s.input}
          autoCapitalize="none"
        />

        <Pressable
          disabled={busy}
          onPress={createColor}
          style={[
            s.button,
            busy && { opacity: 0.5 },
          ]}
        >
          <Text style={s.buttonText}>
            {busy ? "Adding..." : "Add color"}
          </Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  </Modal>
);
}
const s = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#FFF8EF",
  },

  header: {
    padding: 18,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    borderBottomWidth: 1,
    borderColor: "#E9E2D8",
  },

  eyebrow: {
    color: "#B04B1F",
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 1.5,
  },

  title: {
    color: "#17243A",
    fontSize: 22,
    fontWeight: "800",
    marginTop: 3,
  },

  content: {
    padding: 18,
    gap: 12,
    paddingBottom: 50,
  },

  sectionTitle: {
    color: "#17243A",
    fontSize: 18,
    fontWeight: "800",
  },

  colorCard: {
    backgroundColor: "white",
    borderWidth: 1,
    borderColor: "#E9E2D8",
    borderRadius: 14,
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },

  colorPreview: {
    width: 42,
    height: 42,
    borderRadius: 21,
    borderWidth: 1,
    borderColor: "#C7CFD8",
  },

  colorName: {
    color: "#17243A",
    fontSize: 16,
    fontWeight: "700",
  },

  muted: {
    color: "#5D6B7D",
    fontSize: 13,
    lineHeight: 20,
  },

  label: {
    color: "#17243A",
    fontWeight: "700",
    marginTop: 4,
  },

  input: {
    borderWidth: 1,
    borderColor: "#C7CFD8",
    borderRadius: 10,
    padding: 13,
    backgroundColor: "white",
    color: "#17243A",
    minHeight: 46,
  },

  divider: {
    height: 1,
    backgroundColor: "#E9E2D8",
    marginVertical: 8,
  },

  button: {
    backgroundColor: "#C84E1F",
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: "center",
    marginTop: 6,
  },

  buttonText: {
    color: "white",
    fontWeight: "800",
  },

  secondaryButton: {
    backgroundColor: "#F2EDE5",
    paddingHorizontal: 15,
    paddingVertical: 12,
    borderRadius: 12,
  },

  secondaryButtonText: {
    color: "#17243A",
    fontWeight: "700",
  },

  error: {
    color: "#B32929",
    lineHeight: 21,
  },
});