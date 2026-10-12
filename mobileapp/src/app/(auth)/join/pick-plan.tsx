import { useCallback, useEffect, useState } from "react";
import { View } from "react-native";
import { router } from "expo-router";

import { AuthScreen } from "@/components/auth-screen";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/empty-state";
import { ChoiceCard } from "@/components/auth/choice-card";
import { api, ApiError } from "@/lib/api";
import { useJoinStore } from "@/stores/join-store";
import { JOIN_FLOW, flowPosition } from "@/lib/flow";
import type { PublicPlanOut } from "@/types/api";

/** Billing type → the unit shown after the price. */
const PERIOD: Record<string, string> = {
  recurring: "/term",
  one_time_pack: " pack",
  drop_in: " drop-in",
};

function planTerms(plan: PublicPlanOut): string {
  const details = [plan.public_description].filter(Boolean) as string[];
  if (plan.audience === "student") details.push("Student plan");
  if (plan.audience === "family" && plan.family_capacity) details.push(`Covers up to ${plan.family_capacity} people`);
  if (plan.billing_type === "one_time_pack" && plan.pack_size) details.push(`${plan.pack_size} class credits${plan.validity_days ? ` · valid ${plan.validity_days} days` : ""}`);
  if (plan.included_credits) details.push(`${plan.included_credits} visits per term`);
  if (plan.off_peak_start && plan.off_peak_end) details.push(`Off-peak ${plan.off_peak_start}–${plan.off_peak_end}`);
  return details.join(" · ");
}

export default function PickPlan() {
  const { orgCode, selectedPlanId, setSelectedPlan } = useJoinStore();
  const [plans, setPlans] = useState<PublicPlanOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(selectedPlanId ?? "");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<PublicPlanOut[]>(
        `/memberships/signup/plans?org_code=${orgCode}`,
      );
      setPlans(data);
      // Preselect the featured plan, or the first one. Landing on this screen
      // with nothing selected makes Continue look broken.
      if (data.length > 0) {
        setSelected((current) => current || (data.find((p) => p.featured) ?? data[0]).id);
      }
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Couldn't load plans. Check your connection.",
      );
    } finally {
      setLoading(false);
    }
  }, [orgCode]);

  useEffect(() => {
    if (orgCode) load();
  }, [orgCode, load]);

  if (!orgCode) {
    router.replace("/(auth)/register/org-code");
    return null;
  }

  const handleContinue = () => {
    if (!selected) return;
    setSelectedPlan(selected);
    router.push("/(auth)/join/pay");
  };

  return (
    <AuthScreen
      title="Choose a plan"
      subtitle="Pick what fits how often you train. You can switch later."
      back
      progress={flowPosition(JOIN_FLOW, "/(auth)/join/pick-plan")}
      footer={
        plans.length > 0 ? (
          <Button disabled={!selected} onPress={handleContinue}>
            Continue
          </Button>
        ) : undefined
      }
    >
      {error ? (
        <View className="mb-5">
          <Alert type="error" message={error} onDismiss={() => setError(null)} />
        </View>
      ) : null}

      {loading ? (
        <View className="items-center py-16">
          <Spinner />
        </View>
      ) : plans.length === 0 ? (
        <EmptyState
          title={error ? "Couldn't load plans" : "No plans yet"}
          message={
            error
              ? "Something went wrong reaching your organization."
              : "This organization hasn't published any plans yet. Check back soon."
          }
          action={
            <Button variant="secondary" onPress={load}>
              Try again
            </Button>
          }
        />
      ) : (
        <View className="gap-3">
          {plans.map((plan) => (
            <ChoiceCard
              key={plan.id}
              price={`${plan.currency} ${plan.price}`}
              period={plan.billing_type === "recurring" ? `/${plan.cycle_length ?? 1} ${plan.cycle_unit ?? "month"}${(plan.cycle_length ?? 1) === 1 ? "" : "s"}` : PERIOD[plan.billing_type] ?? ""}
              name={plan.name}
              detail={planTerms(plan)}
              featured={plan.featured}
              selected={selected === plan.id}
              onPress={() => setSelected(plan.id)}
            />
          ))}
        </View>
      )}
    </AuthScreen>
  );
}
