import "@/global.css";

import { useEffect, useMemo } from "react";
import { DarkTheme, DefaultTheme, ThemeProvider } from "@react-navigation/native";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useFonts } from "expo-font";
import { Saira_800ExtraBold } from "@expo-google-fonts/saira";
import * as SplashScreen from "expo-splash-screen";
import * as SystemUI from "expo-system-ui";
import { useColorScheme } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { HeroUINativeProvider } from "heroui-native";
import { StripeProvider } from "@stripe/stripe-react-native";

import { useAuthStore } from "@/stores/auth-store";
import { toOrgSummary, useOrgStore } from "@/stores/org-store";
import { useNotificationStore } from "@/stores/notification-store";
import { api } from "@/lib/api";
import { restartRealtime, stopRealtime } from "@/lib/realtime";
import { cleanupStaleKeys } from "@/lib/idempotency";
import { BlurTargetProvider } from "@/components/blur-target";
import { getPalette } from "@/lib/theme";
import type { OrgSummaryResponse, UnreadCountOut } from "@/types/api";

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const isDark = colorScheme === "dark";
  const palette = getPalette(isDark);

  /* The brand display face — Saira ExtraBold (Omnibus-Type, via Google Fonts),
     an athletic, slightly geometric sans used for the ACRON wordmark. Loaded
     here so the splash holds until it's ready. */
  const [fontsLoaded] = useFonts({
    Saira: Saira_800ExtraBold,
  });

  const { isHydrated, isLoading, clearSession, setSession, accessToken } = useAuthStore();
  const { setOrgs, setActiveOrg } = useOrgStore();
  const activeOrgId = useOrgStore((s) => s.activeOrg?.id);
  const setUnreadCount = useNotificationStore((s) => s.setUnreadCount);

  /**
   * React Navigation paints every screen with its own theme background before
   * our views mount. Its default is a light gray regardless of color scheme, so
   * without this the app flashes — and shows — white behind HeroUI's dark
   * surfaces. Same reason for the system window color underneath.
   */
  const navTheme = useMemo(() => {
    const base = isDark ? DarkTheme : DefaultTheme;
    return {
      ...base,
      colors: {
        ...base.colors,
        background: palette.background,
        card: palette.surface,
        text: palette.foreground,
        border: palette.border,
        primary: palette.accent,
      },
    };
  }, [isDark, palette]);

  useEffect(() => {
    SystemUI.setBackgroundColorAsync(palette.background);
  }, [palette.background]);

  useEffect(() => {
    if (!isHydrated || isLoading || !fontsLoaded) return;

    const init = async () => {
      try {
        cleanupStaleKeys();
        const rows = await api.get<OrgSummaryResponse[]>("/auth/my-organizations");
        const orgs = rows.map(toOrgSummary);
        setOrgs(orgs);
        if (orgs.length > 0) {
          setActiveOrg(orgs[0]);
        }
      } catch {
        // Not authenticated or network error — fine
      } finally {
        SplashScreen.hideAsync();
      }
    };
    init();
  }, [isHydrated, isLoading, fontsLoaded]);

  /**
   * Realtime + badge seeding. Once we have both a session and an active org,
   * fetch the server-side unread count (server is the source of truth) and
   * open the WebSocket so `notification.created` events bump the badge. On
   * logout or org switch, tear the socket down and reset the badge.
   */
  useEffect(() => {
    if (!accessToken || !activeOrgId) {
      stopRealtime();
      setUnreadCount(0);
      return;
    }
    restartRealtime();
    api.get<UnreadCountOut>("/notifications/unread-count").then(
      (r) => setUnreadCount(r.count),
      () => undefined,
    );
    return () => stopRealtime();
  }, [accessToken, activeOrgId, setUnreadCount]);

  return (
    <StripeProvider publishableKey={process.env.EXPO_PUBLIC_STRIPE_PUBLISHABLE_KEY ?? "pk_test_placeholder"}>
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: palette.background }}>
      <HeroUINativeProvider>
        <SafeAreaProvider>
          <ThemeProvider value={navTheme}>
            <BlurTargetProvider>
              <StatusBar style={isDark ? "light" : "dark"} />
              <Stack
                screenOptions={{
                  headerShown: false,
                  animation: "slide_from_right",
                  contentStyle: { backgroundColor: palette.background },
                }}
              >
                <Stack.Screen name="index" />
                <Stack.Screen name="(auth)" />
                <Stack.Screen name="(member)" />
                <Stack.Screen name="(staff)" />
                <Stack.Screen name="(admin)" />
                <Stack.Screen name="gym-settings/rotate-code" options={{ animation: "slide_from_right" }} />
                <Stack.Screen name="gym-settings/stripe" options={{ animation: "slide_from_right" }} />
                <Stack.Screen name="gym-settings/revenue" options={{ animation: "slide_from_right" }} />
                <Stack.Screen name="notifications" options={{ animation: "slide_from_right" }} />
              </Stack>
            </BlurTargetProvider>
          </ThemeProvider>
        </SafeAreaProvider>
      </HeroUINativeProvider>
    </GestureHandlerRootView>
    </StripeProvider>
  );
}
