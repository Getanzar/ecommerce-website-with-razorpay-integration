import { File } from "expo-file-system";

/** Expo 57 fetch encodes Blob/File bytes, not React Native's old { uri } parts. */
export function appendPhoto(form: FormData, field: string, asset: { uri: string }) {
  const file = new File(asset.uri);
  if (!file.exists || file.size === 0) {
    throw new Error("The selected photo is no longer available. Select it again before uploading.");
  }
  if (file.size > 8 * 1024 * 1024) {
    throw new Error("Choose a photo smaller than 8 MB.");
  }
  form.append(field, file);
}
