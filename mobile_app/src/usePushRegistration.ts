import { useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import Constants from "expo-constants";
import * as Device from "expo-device";

import { deactivatePushDevice, registerPushDevice } from "./api";

const isExpoGo = Constants.appOwnership === "expo";

type State = "idle" | "registered" | "unavailable" | "denied" | "error";

/** Registers only on physical development/production builds, never Expo Go or web. */
export default function usePushRegistration(token: string | null) {
  const [state, setState] = useState<State>("idle");
  const registered = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const register = async () => {
      if (!token || !Device.isDevice || isExpoGo) {
        if (!cancelled) setState("unavailable");
        return;
      }
      try {
        // Importing the public barrel in Expo Go initializes a remote-push listener.
        // Load it only in a build that contains the required native push module.
        const Notifications = await import("expo-notifications");
        Notifications.setNotificationHandler({
          handleNotification: async () => ({
            shouldShowBanner: true,
            shouldShowList: true,
            shouldPlaySound: true,
            shouldSetBadge: false,
          }),
        });
        if (Platform.OS === "android") {
          await Notifications.setNotificationChannelAsync("orders", { name: "Order updates", importance: Notifications.AndroidImportance.HIGH });
        }
        const current = await Notifications.getPermissionsAsync();
        const permission = current.granted
          ? current
          : await Notifications.requestPermissionsAsync();
        if (!permission.granted) {
          if (!cancelled) setState("denied");
          return;
        }
        if (Platform.OS === "android") {
          await Notifications.setNotificationChannelAsync("orders", {
            name: "Order updates",
            importance: Notifications.AndroidImportance.HIGH,
            vibrationPattern: [0, 250, 250, 250],
          });
        }
        const projectId = process.env.EXPO_PUBLIC_EAS_PROJECT_ID || Constants.expoConfig?.extra?.eas?.projectId;
        if (!projectId) {
          if (!cancelled) setState("unavailable");
          return;
        }
        const expoToken = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
        await registerPushDevice(token, expoToken, Platform.OS);
        if (cancelled) { await deactivatePushDevice(token, expoToken); return; }
        registered.current = expoToken;
        if (!cancelled) setState("registered");
      } catch {
        if (!cancelled) setState("error");
      }
    };
    register();
    return () => {
      cancelled = true;
      const expoToken = registered.current;
      registered.current = null;
      if (expoToken && token) deactivatePushDevice(token, expoToken).catch(() => undefined);
    };
  }, [token]);

  return state;
}
