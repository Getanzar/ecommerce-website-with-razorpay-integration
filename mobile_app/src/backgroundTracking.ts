import * as TaskManager from "expo-task-manager";
import * as Location from "expo-location";
import * as SecureStore from "expo-secure-store";
import { API_URL } from "./api";
import { reportError } from "./telemetry";

const TASK = "ziyamart-delivery-location";
const STORAGE = "ziyamart_tracking";
type Tracking = { job: number; token: string; until: number };
export async function stopTracking() {
  await SecureStore.deleteItemAsync(STORAGE);
  if (await Location.hasStartedLocationUpdatesAsync(TASK)) await Location.stopLocationUpdatesAsync(TASK);
}
export async function trackedJob(): Promise<number | null> {
  const value = await SecureStore.getItemAsync(STORAGE);
  return value ? (JSON.parse(value) as Tracking).job : null;
}
TaskManager.defineTask<{ locations: Location.LocationObject[] }>(TASK, async ({ data, error }) => {
  if (error) { reportError(error, "background_location"); return; }
  const stored = await SecureStore.getItemAsync(STORAGE);
  if (!stored) { await stopTracking(); return; }
  const state: Tracking = JSON.parse(stored);
  if (Date.now() > state.until) { await stopTracking(); return; }
  // Only the newest fix is useful. Do not queue private location history offline.
  const fix = data?.locations[data.locations.length - 1];
  if (!fix || Date.now() - fix.timestamp > 120000) return;
  try {
    const response = await fetch(`${API_URL}/partners/rider/jobs/${state.job}/location/`, {
      method: "POST", headers: { Authorization: `Token ${state.token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ latitude: fix.coords.latitude.toFixed(6), longitude: fix.coords.longitude.toFixed(6), accuracy: Math.round(fix.coords.accuracy ?? 0) }),
      signal: AbortSignal.timeout(15000),
    });
    if ([400, 401, 403, 404].includes(response.status)) await stopTracking();
  } catch (e) { reportError(e, "location_upload"); }
});
export async function startTracking(token: string, job: number) {
  if (!(await Location.requestForegroundPermissionsAsync()).granted) throw new Error("Location permission was denied.");
  if (!(await Location.requestBackgroundPermissionsAsync()).granted) throw new Error("Allow background location in device settings to track an active delivery.");
  await stopTracking();
  await SecureStore.setItemAsync(STORAGE, JSON.stringify({ token, job, until: Date.now() + 8 * 60 * 60 * 1000 }), { keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY });
  try {
    await Location.startLocationUpdatesAsync(TASK, { accuracy: Location.Accuracy.High, timeInterval: 15000, distanceInterval: 30, pausesUpdatesAutomatically: true, showsBackgroundLocationIndicator: true, foregroundService: { notificationTitle: "Delivery tracking active", notificationBody: "Sharing your active delivery location. Stop sharing from the rider job." } });
  } catch (e) { await stopTracking(); throw e; }
}
