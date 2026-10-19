import React, { useState } from "react";
import { View } from "react-native";
import { Text } from "heroui-native";

import { AppScreen } from "@/components/app-screen";
import { DashboardError } from "@/components/dashboard-states";
import { DashboardSkeleton } from "@/components/dashboard-skeleton";
import { SectionCard } from "@/components/section-card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/alert";
import { useGet } from "@/hooks/use-api";
import { api, ApiError } from "@/lib/api";

type Milestone = {
  day: number;
  code: string;
  title: string;
  member_action: string | null;
  status: "pending" | "completed" | "skipped" | "locked";
  completed_at: string | null;
  notes: string | null;
};
type Journey = {
  status: string;
  current_day: number;
  total_days: number;
  started_at: string;
  visits_total: number;
  visits_last_7d: number;
  classes_attended: number;
  at_risk: boolean;
  milestones: Milestone[];
};

export default function MemberOnboardingScreen() {
  const journey = useGet<Journey>("/onboarding/me", ["membership.changed", "attendance.recorded"]);
  const [busyCode, setBusyCode] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const complete = async (code: string) => {
    setBusyCode(code);
    setMessage(null);
    setError(null);
    try {
      await api.post("/onboarding/me/milestones/complete", { code });
      setMessage("Milestone saved. Keep up the good work.");
      journey.refetch();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not update your journey.");
    } finally {
      setBusyCode(null);
    }
  };

  const missingJourney = journey.error?.toLowerCase().includes("no onboarding journey") ?? false;
  const journeyActive = journey.data?.status === "active";
  const percent = journey.data ? Math.min(100, Math.round((journey.data.current_day / journey.data.total_days) * 100)) : 0;

  return (
    <AppScreen title="Your first 90 days" subtitle="Small steps help make training a lasting habit." showBackButton>
      {journey.loading ? <DashboardSkeleton /> : journey.error && !missingJourney ? (
        <DashboardError message={journey.error} onRetry={journey.refetch} />
      ) : missingJourney ? (
        <View className="rounded-2xl bg-surface-secondary p-5">
          <Text type="body" weight="semibold" className="text-foreground">Your journey is getting ready</Text>
          <Text type="body-sm" color="muted" className="mt-2">Your gym will add your 90-day milestones once your membership is active.</Text>
        </View>
      ) : journey.data ? (
        <>
          <View className="mb-5 rounded-2xl bg-surface p-5">
            <View className="flex-row items-start justify-between gap-3">
              <View className="flex-1">
                <Text type="body-sm" color="muted">YOUR PROGRESS</Text>
                <Text type="h2" className="mt-1 text-foreground">Day {Math.min(journey.data.current_day, journey.data.total_days)} of {journey.data.total_days}</Text>
              </View>
              <Badge tone={journey.data.status === "completed" ? "success" : journey.data.status === "paused" ? "warning" : "info"} label={journey.data.status.replace("_", " ")} />
            </View>
            <View className="mt-4 h-2 overflow-hidden rounded-full bg-surface-tertiary">
              <View className="h-full rounded-full bg-accent" style={{ width: `${percent}%` }} />
            </View>
            <View className="mt-4 flex-row justify-between">
              <Text type="body-xs" color="muted">{journey.data.visits_total} visits</Text>
              <Text type="body-xs" color="muted">{journey.data.classes_attended} classes</Text>
              <Text type="body-xs" color="muted">{journey.data.visits_last_7d} this week</Text>
            </View>
          </View>

          {journey.data.at_risk ? <View className="mb-5"><Alert type="info" message="We haven’t seen a visit this week. Reach out to your gym if you need help getting back into a routine." /></View> : null}
          {message ? <View className="mb-4"><Alert type="success" message={message} /></View> : null}
          {error ? <View className="mb-4"><Alert type="error" message={error} onDismiss={() => setError(null)} /></View> : null}

          <SectionCard title="Your milestones">
            <View className="gap-3">
              {journey.data.milestones.map((milestone) => {
                const done = milestone.status === "completed" || milestone.status === "skipped";
                const locked = milestone.status === "locked";
                return (
                  <View key={milestone.code} className="rounded-2xl bg-surface p-4">
                    <View className="flex-row items-start justify-between gap-3">
                      <View className="flex-1">
                        <Text type="body-xs" color="muted">DAY {milestone.day}</Text>
                        <Text type="body" weight="semibold" className="mt-1 text-foreground">{milestone.title}</Text>
                        {milestone.member_action ? <Text type="body-sm" color="muted" className="mt-1">{milestone.member_action}</Text> : null}
                      </View>
                      <Badge tone={done ? "success" : locked ? "neutral" : "info"} label={done ? "Done" : locked ? "Upcoming" : "Next step"} />
                    </View>
                    {milestone.status === "pending" ? (
                      <View className="mt-3 items-start"><Button loading={busyCode === milestone.code} disabled={busyCode !== null || !journeyActive} variant="secondary" onPress={() => void complete(milestone.code)}>Mark done</Button></View>
                    ) : null}
                  </View>
                );
              })}
            </View>
          </SectionCard>
        </>
      ) : null}
    </AppScreen>
  );
}
