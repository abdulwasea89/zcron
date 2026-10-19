import { Tabs } from "expo-router";
import type { BottomTabNavigationOptions } from "@react-navigation/bottom-tabs";
import type { TabSymbol } from "@/components/tab-icon";
import { tabScreenLayout, useTabIcon, useTabScreenOptions } from "@/components/tab-bar";
import { RequireAuth } from "@/components/auth-guard";
import { getIndustry } from "@/lib/industries";
import { useOrgStore } from "@/stores/org-store";

const SYMBOLS = {
  dashboard: { glyph: "home" },
  classes: { glyph: "barbell" },
  space: { glyph: "business" },
  payments: { glyph: "card" },
  profile: { glyph: "person" },
} satisfies Record<string, TabSymbol>;

/**
 * A tab the current member isn't offered: removed from the bar (display none
 * + no button) while the route stays registered. Office seat-holders don't
 * pay individually (their company is billed), so the gym "Classes" and
 * "Payments" tabs hide for them and a "Space" booking tab appears instead.
 */
const HIDDEN: BottomTabNavigationOptions = {
  tabBarItemStyle: { display: "none" },
  tabBarButton: () => null,
};

export default function MemberLayout() {
  const screenOptions = useTabScreenOptions();
  const icon = useTabIcon();
  const activeOrg = useOrgStore((s) => s.activeOrg);
  const isOffice = getIndustry(activeOrg?.industry).key === "office";

  return (
    <RequireAuth>
      <Tabs screenOptions={screenOptions} screenLayout={tabScreenLayout}>
        <Tabs.Screen
          name="dashboard"
          options={{ title: "Home", tabBarIcon: icon(SYMBOLS.dashboard) }}
        />
        <Tabs.Screen
          name="classes"
          options={isOffice ? HIDDEN : { title: "Classes", tabBarIcon: icon(SYMBOLS.classes) }}
        />
        <Tabs.Screen
          name="space"
          options={isOffice ? { title: "Space", tabBarIcon: icon(SYMBOLS.space) } : HIDDEN}
        />
        <Tabs.Screen
          name="payments"
          options={isOffice ? HIDDEN : { title: "Payments", tabBarIcon: icon(SYMBOLS.payments) }}
        />
        <Tabs.Screen
          name="profile"
          options={{ title: "Profile", tabBarIcon: icon(SYMBOLS.profile) }}
        />
        <Tabs.Screen name="onboarding" options={HIDDEN} />
        <Tabs.Screen name="membership-pause" options={HIDDEN} />
        <Tabs.Screen name="membership-change" options={HIDDEN} />
      </Tabs>
    </RequireAuth>
  );
}
