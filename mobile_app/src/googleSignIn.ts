import * as Crypto from "expo-crypto";
import * as WebBrowser from "expo-web-browser";
import * as Device from "expo-device";
import { API_URL, AuthResponse, request } from "./api";

const randomSecret = async () => Array.from(await Crypto.getRandomBytesAsync(32), byte => byte.toString(16).padStart(2, "0")).join("");

/** Server holds Google credentials; an intercepted app link cannot redeem PKCE. */
export async function googleSignIn(token?: string): Promise<AuthResponse | null> {
  const verifier = await randomSecret();
  const state = await randomSecret();
  const challenge = (await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, verifier, { encoding: Crypto.CryptoEncoding.BASE64 })).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const start = await request<{ url: string }>("/auth/google/start/", { method: "POST", body: JSON.stringify({ challenge, state }) }, token);
  if (new URL(start.url).origin !== new URL(API_URL).origin || !start.url.startsWith(`${API_URL}/auth/google/browser/?`)) throw new Error("Invalid Google sign-in destination.");
  const result = await WebBrowser.openAuthSessionAsync(start.url, "ziyamart://auth/callback");
  if (result.type !== "success") return null;
  const url = new URL(result.url);
  if (url.protocol !== "ziyamart:" || url.hostname !== "auth" || url.pathname !== "/callback" || url.searchParams.get("state") !== state) throw new Error("This sign-in response could not be verified. Please try again.");
  if (url.searchParams.get("error")) throw new Error(url.searchParams.get("error")!);
  const code = url.searchParams.get("code");
  if (!code) throw new Error("Google sign-in was not completed.");
  const response = await request<AuthResponse>("/auth/google/exchange/", { method: "POST", body: JSON.stringify({ code, verifier, device_name: Device.modelName || "Mobile device" }) }, token);
  return token ? { ...response, token } : response;
}
