import React, { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Image, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { getProfile, requestProfileEmail, updateProfile, User, verifyProfileEmail } from "./api";
import { appendPhoto } from "./uploads";
import { googleSignIn } from "./googleSignIn";

const errorMessage = (error: any) => {
  const details = error.details?.errors || error.details;
  return details && typeof details === "object" ? Object.entries(details).map(([field, value]) => `${field}: ${Array.isArray(value) ? value.join(" ") : value}`).join("\n") : error.message || "Please try again.";
};

export default function ProfileEditor({ token, onSaved }: { token: string; onSaved?: (user: User) => void }) {
  const [profile, setProfile] = useState<User | null>(null);
  const [photo, setPhoto] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [email, setEmail] = useState("");
  const [pendingEmail, setPendingEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [resendAt, setResendAt] = useState(0);
  const [remaining, setRemaining] = useState(0);
  useEffect(() => { let active = true; getProfile(token).then(user => { if (active) { setProfile(user); setEmail(user.email); } }).catch(err => { if (active) setError(errorMessage(err)); }); return () => { active = false; }; }, [token, retry]);
  useEffect(() => { const tick = () => setRemaining(Math.max(0, Math.ceil((resendAt - Date.now()) / 1000))); tick(); const timer = setInterval(tick, 1000); return () => clearInterval(timer); }, [resendAt]);
  const run = async (action: () => Promise<void>) => { if (busy) return; setBusy(true); setError(""); try { await action(); } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); } };
  const saved = (user: User) => { setProfile(user); onSaved?.(user); };
  const pickPhoto = () => run(async () => {
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], allowsEditing: true, aspect: [1, 1], quality: 0.8 });
    if (!result.canceled) { if ((result.assets[0].fileSize || 0) > 5 * 1024 * 1024) throw new Error("Choose a photo smaller than 5 MB."); setPhoto(result.assets[0]); }
  });
  if (!profile) return <View>{error ? <><Text style={s.error}>{error}</Text><Pressable onPress={() => { setError(""); setRetry(retry + 1); }}><Text style={s.link}>Try again</Text></Pressable></> : <ActivityIndicator />}</View>;
  const field = (key: "first_name" | "last_name" | "username" | "phone" | "date_of_birth", title: string, numeric = false) => <View style={s.field} key={key}><Text style={s.label}>{title}</Text><TextInput accessibilityLabel={title} style={s.input} value={profile[key] || ""} editable={!busy} autoCapitalize={key === "username" ? "none" : "words"} keyboardType={numeric ? "phone-pad" : "default"} placeholder={key === "date_of_birth" ? "YYYY-MM-DD" : title} onChangeText={value => setProfile({ ...profile, [key]: value })} /></View>;
  return <View style={s.page}>
    <View style={s.intro}><Text style={s.eyebrow}>YOUR ZIYAMART ACCOUNT</Text><Text style={s.title}>Make yourself at home</Text><Text style={s.copy}>Add your details whenever you're ready. Your email is all you need to get started.</Text></View>
    <Pressable accessibilityLabel="Choose profile photo" disabled={busy} onPress={pickPhoto} style={s.photoButton}>{photo?.uri || profile.profile_picture_url ? <Image source={{ uri: photo?.uri || profile.profile_picture_url! }} style={s.photo} /> : <View style={[s.photo, s.avatar]}><Text style={s.initial}>{(profile.first_name || profile.email).charAt(0).toUpperCase()}</Text></View>}<Text style={s.link}>Change photo</Text></Pressable>
    {field("first_name", "First name")}{field("last_name", "Last name")}{field("username", "Username")}{field("phone", "Mobile number", true)}{field("date_of_birth", "Date of birth")}
    <Text style={s.label}>Gender (optional)</Text><View style={s.choices}>{["", "Male", "Female", "Other", "Prefer not to say"].map(gender => <Pressable key={gender} disabled={busy} accessibilityRole="radio" accessibilityState={{ checked: profile.gender === gender }} onPress={() => setProfile({ ...profile, gender })} style={[s.chip, profile.gender === gender && s.active]}><Text style={s.label}>{gender || "Not selected"}</Text></Pressable>)}</View>
    {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
    <Pressable disabled={busy} style={[s.button, busy && s.disabled]} onPress={() => run(async () => { const data = new FormData(); for (const key of ["first_name", "last_name", "username", "phone", "gender", "date_of_birth"] as const) data.append(key, profile[key] || ""); if (photo) appendPhoto(data, "profile_picture", photo); saved(await updateProfile(token, data)); setPhoto(null); Alert.alert("Profile saved", "Your personal details are up to date."); })}><Text style={s.buttonText}>{busy ? "Please wait…" : "Save personal details"}</Text></Pressable>
    <View style={s.card}><Text style={s.heading}>Email & sign-in</Text><Text style={s.copy}>Current email: {profile.email}{profile.email_verified ? " · Verified" : ""}</Text><Text style={s.copy}>A new email becomes your login email only after verification.</Text><TextInput accessibilityLabel="New email address" style={s.input} autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} editable={!busy} />
      <Pressable disabled={busy || remaining > 0 || email.trim().toLowerCase() === profile.email.toLowerCase()} onPress={() => run(async () => { const result = await requestProfileEmail(token, email); setPendingEmail(result.email); setOtp(""); setResendAt(Date.now() + 60000); })}><Text style={[s.link, (busy || remaining > 0 || email.trim().toLowerCase() === profile.email.toLowerCase()) && s.disabled]}>{remaining ? `Send again in ${remaining}s` : "Send verification code"}</Text></Pressable>
      {!!pendingEmail && <><Text style={s.copy}>Enter the code sent to {pendingEmail}</Text><TextInput accessibilityLabel="Email verification code" style={s.input} keyboardType="number-pad" value={otp} onChangeText={setOtp} maxLength={6} editable={!busy} /><Pressable disabled={busy || otp.length !== 6} style={s.button} onPress={() => run(async () => { const user = await verifyProfileEmail(token, otp); saved(user); setEmail(user.email); setPendingEmail(""); setOtp(""); Alert.alert("Email verified", "Use your new email next time you sign in."); })}><Text style={s.buttonText}>Verify new email</Text></Pressable></>}
      <Pressable disabled={busy} onPress={() => run(async () => { const result = await googleSignIn(token); if (result) { saved(await getProfile(token)); Alert.alert("Google connected", "You can now sign in with this Google account."); } })}><Text style={s.link}>Connect Google account</Text></Pressable>
    </View>
  </View>;
}

const s = StyleSheet.create({ page: { gap: 18, paddingBottom: 30 }, intro: { gap: 8 }, eyebrow: { color: "#0F8B6D", fontSize: 11, fontWeight: "800", letterSpacing: 1.5 }, title: { color: "#17243A", fontSize: 27, fontWeight: "800" }, copy: { color: "#667085", lineHeight: 22, fontSize: 14 }, photoButton: { alignSelf: "flex-start", gap: 10, alignItems: "center" }, photo: { width: 88, height: 88, borderRadius: 44 }, avatar: { backgroundColor: "#E8F5EE", alignItems: "center", justifyContent: "center" }, initial: { fontSize: 32, fontWeight: "800", color: "#0F8B6D" }, field: { gap: 7 }, label: { color: "#344054", fontWeight: "600", fontSize: 13 }, input: { minHeight: 50, backgroundColor: "#F8FAFC", borderColor: "#DFE5EB", borderWidth: 1, borderRadius: 13, paddingHorizontal: 14, color: "#17243A" }, choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 }, chip: { borderWidth: 1, borderColor: "#E4E7EC", padding: 10, borderRadius: 20 }, active: { backgroundColor: "#E8F5EE", borderColor: "#0F8B6D" }, button: { backgroundColor: "#0F8B6D", padding: 16, borderRadius: 14, alignItems: "center" }, buttonText: { color: "white", fontWeight: "700" }, link: { color: "#0F8B6D", fontWeight: "700", paddingVertical: 8 }, card: { borderWidth: 1, borderColor: "#E4E7EC", padding: 18, borderRadius: 20, gap: 14 }, heading: { fontSize: 19, color: "#17243A", fontWeight: "800" }, error: { color: "#B42318", lineHeight: 21 }, disabled: { opacity: 0.45 } });
