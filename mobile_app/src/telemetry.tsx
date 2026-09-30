import React from "react";
import { Pressable, Text, View } from "react-native";

type Reporter = (event: { name: string; fatal: boolean; context?: string }) => void;
let reporter: Reporter = () => {};
/** Bind Sentry/Crashlytics in the native entry point. Never forward tokens or API bodies. */
export function configureCrashReporter(callback: Reporter) { reporter = callback; }
export function reportError(error: unknown, context: string, fatal = false) {
  try { reporter({ name: error instanceof Error ? error.name : "UnknownError", fatal, context }); } catch { /* Reporting cannot break the app. */ }
}
export class AppErrorBoundary extends React.Component<React.PropsWithChildren, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) { reportError(error, "react_render", true); }
  render() {
    if (!this.state.failed) return this.props.children;
    return <View style={{ flex: 1, padding: 32, justifyContent: "center" }}><Text accessibilityRole="alert">Something went wrong. Your orders are saved on your account.</Text><Pressable accessibilityRole="button" style={{ paddingVertical: 20 }} onPress={() => this.setState({ failed: false })}><Text>Try again</Text></Pressable></View>;
  }
}
