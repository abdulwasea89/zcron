import React from "react";
import { Pressable, Share, View } from "react-native";
import { Text } from "heroui-native";
import { router } from "expo-router";

import { AppScreen } from "@/components/app-screen";
import { DashboardSkeleton } from "@/components/dashboard-skeleton";
import { DashboardError } from "@/components/dashboard-states";
import { SectionCard } from "@/components/section-card";
import { Icon } from "@/components/icon";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Stagger } from "@/components/motion";
import { useGet } from "@/hooks/use-api";
import { useOrgStore } from "@/stores/org-store";
import { getIndustry } from "@/lib/industries";
import { formatDay, formatTime, firstName, greeting, money } from "@/lib/format";
import type {
  ClassSessionOut,
  InvoiceOut,
  MeResponse,
  OrganizationOut,
  ProfileOut,
} from "@/types/api";

type MemberStatus = string;

type MemberReferralOverview = {
  enabled: boolean;
  code: string | null;
  organization_code: string;
  reward_description: string;
  referrals: { id: string; referred_name: string | null; status: string }[];
  earned_rewards: { id: string; description: string; status: string }[];
};

const STATUS_BANNER: Partial<
  Record<MemberStatus, { tone: "accent" | "success" | "warning" | "danger" | "neutral"; title: string; message: string }>
> = {
  active: { tone: "success", title: "Membership active", message: "You’re all set — see you at the gym." },
  grace: { tone: "warning", title: "Payment due", message: "Your membership is in its grace period. Renew now to keep your spot." },
  pending_payment: { tone: "accent", title: "Complete your payment", message: "Finish payment to activate your membership." },
  pending_approval: { tone: "neutral", title: "Membership under review", message: "The gym will notify you once it’s approved." },
  expired: { tone: "danger", title: "Membership expired", message: "Your access is paused. Renew to continue training." },
  frozen: { tone: "warning", title: "Membership frozen", message: "Your membership is temporarily frozen." },
  cancelled: { tone: "neutral", title: "Membership cancelled", message: "Your membership is no longer active." },
  banned: { tone: "danger", title: "Access blocked", message: "Please contact the gym for support." },
};

const INVOICE_TONE: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
  paid: "success",
  partial: "warning",
  sent: "info",
  draft: "neutral",
  overdue: "danger",
  void: "neutral",
};

function upcoming(sessions: ClassSessionOut[]): ClassSessionOut[] {
  const now = Date.now();
  return sessions
    .filter((s) => !s.cancelled && new Date(s.starts_at).getTime() >= now)
    .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime())
    .slice(0, 3);
}

export default function Screen_dashboard() {
  const activeOrg = useOrgStore((s) => s.activeOrg);
  const isOffice = getIndustry(activeOrg?.industry).key === "office";

  const realtime = ["membership.changed", "payment.recorded", "plan.changed", "class.changed", "gym_status.changed"];

  const me = useGet<MeResponse>("/auth/me", realtime);
  const profile = useGet<ProfileOut>("/auth/me/profile", realtime);
  const org = useGet<OrganizationOut>("/organizations/me", realtime);
  // A seat-holder's company is billed on invoices, not via a personal card, so
  // the office home reads the company's open invoices and skips the gym class
  // schedule entirely.
  const classes = useGet<ClassSessionOut[]>(isOffice ? null : "/classes", ["class.changed"]);
  const bills = useGet<InvoiceOut[]>(isOffice ? "/invoices/my-company" : null, ["payment.recorded", "invoice.sent"]);
  const referrals = useGet<MemberReferralOverview>("/referrals/me");

  const loading = me.loading || profile.loading || org.loading || classes.loading || bills.loading;
  const error = me.error ?? profile.error ?? org.error ?? classes.error ?? bills.error;

  const orgName = org.data?.name ?? activeOrg?.name ?? "";
  const status = me.data?.member_status ?? null;
  const banner = status ? STATUS_BANNER[status] : null;

  const sessions = upcoming(classes.data ?? []);
  const greetingName = firstName(profile.data?.full_name);

  const refresh = () => {
    me.refetch();
    profile.refetch();
    org.refetch();
    classes.refetch();
    bills.refetch();
  };

  const goTo = (path: "/classes" | "/payments" | "/space") => () => router.navigate(path);

  const invoices = isOffice ? (bills.data ?? []) : [];

  return (
    <AppScreen
      title={`${greeting()}, ${greetingName}`}
      subtitle={orgName || activeOrg?.org_code || "Your gym"}
    >
      {loading ? (
        <DashboardSkeleton />
      ) : error ? (
        <DashboardError message={error} onRetry={refresh} />
      ) : isOffice ? (
        <>
          <Stagger gap={80}>
            <View className="mb-6">
              <SeatBanner orgName={orgName} status={status} />
            </View>

            <SectionCard title="Quick actions">
              <View className="gap-3">
                <Button onPress={goTo("/space")}>
                  Book a desk or room
                </Button>
              </View>
            </SectionCard>

            <SectionCard
              title="Your company’s bills"
              action={invoices.length > 0 ? <Badge tone="warning" label={`${invoices.length} open`} /> : undefined}
            >
              {invoices.length === 0 ? (
                <View className="rounded-2xl bg-surface px-4 py-6">
                  <Text type="body-sm" color="muted" className="text-center">
                    No open invoices — your company is all settled.
                  </Text>
                </View>
              ) : (
                <View className="overflow-hidden rounded-2xl bg-surface">
                  {invoices.map((inv, i) => (
                    <View
                      key={inv.id}
                      className="px-4 py-3.5"
                      style={i > 0 ? { borderTopWidth: 0.5, borderTopColor: "rgba(128,128,128,0.25)" } : undefined}
                    >
                      <View className="flex-row items-center justify-between gap-2">
                        <Text type="body" weight="medium" className="flex-1 text-foreground" numberOfLines={1}>
                          {inv.invoice_number}
                        </Text>
                        <Badge tone={INVOICE_TONE[inv.status] ?? "neutral"} label={inv.status.replace(/_/g, " ")} />
                      </View>
                      <Text type="body-sm" color="muted" className="mt-0.5">
                        {inv.company_name ?? "Your company"} · due {formatDay(inv.due_date)}
                      </Text>
                      <Text type="body" weight="semibold" className="mt-1 text-foreground">
                        {money(inv.total - inv.paid_amount, inv.currency)} due
                      </Text>
                    </View>
                  ))}
                </View>
              )}
            </SectionCard>
          </Stagger>
        </>
      ) : (
        <>
          <Stagger gap={80}>
            <View className="mb-6">
              <MembershipBanner status={status} banner={banner} />
            </View>

            <SectionCard title="Your first 90 days">
              <Pressable onPress={() => router.navigate("/onboarding" as never)} className="rounded-2xl bg-surface p-4 active:opacity-80">
                <View className="flex-row items-center justify-between gap-3">
                  <View className="flex-1">
                    <Text type="body" weight="semibold" className="text-foreground">Build your routine</Text>
                    <Text type="body-sm" color="muted" className="mt-1">See your milestones and next steps.</Text>
                  </View>
                  <Text type="body-sm" className="text-accent">View →</Text>
                </View>
              </Pressable>
            </SectionCard>

            <SectionCard title="Today’s schedule" action={<Pressable onPress={goTo("/classes")} hitSlop={8}><Text type="body-sm" className="text-accent">See all</Text></Pressable>}>
              {sessions.length === 0 ? (
                <EmptyState
                  title="No classes coming up"
                  message="Browse the schedule and book your next session."
                  action={<Button variant="secondary" onPress={goTo("/classes")}>Browse classes</Button>}
                />
              ) : (
                <View className="overflow-hidden rounded-2xl bg-surface">
                  {sessions.map((s, i) => (
                    <Pressable key={s.id} onPress={goTo("/classes")} className="active:opacity-70">
                      <View className="flex-row items-center py-3.5"
                        style={i > 0 ? { borderTopWidth: 0.5, borderTopColor: "rgba(128,128,128,0.25)" } : undefined}>
                        <View className="mr-3 h-10 w-10 items-center justify-center rounded-xl bg-surface-tertiary">
                          <Icon name="figure.strengthtraining.traditional" android="fitness_center" size={20} className="text-accent" />
                        </View>
                        <View className="flex-1">
                          <Text type="body" weight="medium" className="text-foreground">{s.title}</Text>
                          <Text type="body-sm" color="muted" className="mt-0.5">
                            {formatDay(s.starts_at)} · {formatTime(s.starts_at)} ·{" "}
                            {Math.max(s.capacity - s.booked_count, 0)} spots left
                          </Text>
                        </View>
                      </View>
                    </Pressable>
                  ))}
                </View>
              )}
            </SectionCard>

            {referrals.data?.enabled && referrals.data.code ? (
              <SectionCard title="Invite a friend">
                <View className="gap-3 rounded-2xl bg-surface p-4">
                  <Text type="body-sm" color="muted">
                    Share both codes. When your friend joins and pays, you both earn {referrals.data.reward_description}.
                  </Text>
                  <View className="rounded-xl bg-surface-secondary p-3">
                    <Text type="body-xs" color="muted">Your referral code</Text>
                    <Text type="h3" weight="semibold" className="mt-1 text-foreground">{referrals.data.code}</Text>
                  </View>
                  <Button onPress={() => void Share.share({
                    message: `Join ${orgName || "my gym"}! Organization code: ${referrals.data?.organization_code}. Referral code: ${referrals.data?.code}.`,
                  })}>Share invite</Button>
                  <Text type="body-xs" color="muted">
                    {referrals.data.referrals.filter((item) => item.status === "qualified").length} friend{referrals.data.referrals.filter((item) => item.status === "qualified").length === 1 ? "" : "s"} joined · {referrals.data.earned_rewards.filter((reward) => reward.status === "fulfilled").length} reward{referrals.data.earned_rewards.filter((reward) => reward.status === "fulfilled").length === 1 ? "" : "s"} delivered
                  </Text>
                </View>
              </SectionCard>
            ) : null}

            <SectionCard title="Quick actions">
              <View className="gap-3">
                <Button variant="secondary" onPress={goTo("/classes")}>
                  Book a class
                </Button>
                <Button variant="secondary" onPress={goTo("/payments")}>
                  Payments & receipts
                </Button>
                {!isOffice ? <Button variant="secondary" onPress={() => router.navigate("/membership-change")}>
                  Change or cancel membership
                </Button> : null}
                {!isOffice ? (
                  <Button variant="secondary" onPress={() => router.navigate("/membership-pause")}>
                    {status === "frozen" ? "View pause request" : "Request a membership pause"}
                  </Button>
                ) : null}
              </View>
            </SectionCard>
          </Stagger>
        </>
      )}
    </AppScreen>
  );
}

/**
 * Office seat-holder hero. Their company is billed, so there is no personal
 * payment lane — the message points at the Space booking tab instead.
 */
function SeatBanner({ orgName, status }: { orgName: string; status: MemberStatus | null }) {
  const active = status === "active";
  const tone = active ? "success" : status === "frozen" ? "warning" : "danger";
  const tileClass = {
    success: "bg-success text-success-foreground",
    warning: "bg-warning text-warning-foreground",
    danger: "bg-danger text-danger-foreground",
  }[tone];

  return (
    <View className="overflow-hidden rounded-3xl bg-surface">
      <View className="flex-row items-start gap-3 p-4">
        <View className={`h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${tileClass}`}>
          <Icon
            name={active ? "checkmark.circle.fill" : "exclamationmark.triangle.fill"}
            android={active ? "check_circle" : "warning"}
            size={22}
            color="currentColor"
          />
        </View>
        <View className="flex-1 pt-0.5">
          <View className="flex-row items-center justify-between gap-2">
            <Text type="body" weight="semibold" className="text-foreground">
              {active ? "Your seat is active" : `Seat ${(status ?? "").replace(/_/g, " ")}`}
            </Text>
            <Badge tone={active ? "success" : status === "frozen" ? "warning" : "danger"} label={active ? "active" : (status ?? "").replace(/_/g, " ")} />
          </View>
          <Text type="body-sm" color="muted" className="mt-1">
            {active
              ? orgName
                ? `${orgName} — book a desk or room on the Space tab.`
                : "Book a desk or room on the Space tab."
              : "Please contact your space manager."}
          </Text>
        </View>
      </View>
    </View>
  );
}

function MembershipBanner({
  status,
  banner,
}: {
  status: MemberStatus | null;
  banner: (typeof STATUS_BANNER)[MemberStatus] | undefined | null;
}) {
  if (!status) return null;

  const tone = banner?.tone ?? "neutral";
  const badgeTone: "success" | "warning" | "danger" | "info" | "neutral" =
    tone === "accent" ? "info" : tone;
  const tileClass = {
    accent: "bg-accent text-accent-foreground",
    success: "bg-success text-success-foreground",
    warning: "bg-warning text-warning-foreground",
    danger: "bg-danger text-danger-foreground",
    neutral: "bg-surface-tertiary text-foreground",
  }[tone];

  const needsAction = ["grace", "expired", "pending_payment"].includes(status);

  return (
    <View className="overflow-hidden rounded-3xl bg-surface">
      <View className="flex-row items-start gap-3 p-4">
        <View className={`h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${tileClass}`}>
          <Icon
            name={
              tone === "success"
                ? "checkmark.circle.fill"
                : tone === "warning"
                  ? "exclamationmark.triangle.fill"
                  : tone === "danger"
                    ? "exclamationmark.octagon.fill"
                    : "clock.fill"
            }
            android={tone === "success" ? "check_circle" : tone === "warning" ? "warning" : tone === "danger" ? "dangerous" : "schedule"}
            size={22}
            color="currentColor"
          />
        </View>
        <View className="flex-1 pt-0.5">
          <View className="flex-row items-center justify-between gap-2">
            <Text type="body" weight="semibold" className="text-foreground">
              {banner?.title ?? "Membership"}
            </Text>
            <Badge tone={badgeTone} label={status.replace(/_/g, " ")} />
          </View>
          <Text type="body-sm" color="muted" className="mt-1">
            {banner?.message}
          </Text>
          {needsAction ? (
            <View className="mt-3 flex-row gap-2">
              <Button size="sm" onPress={() => router.navigate("/payments")}>
                Pay now
              </Button>
              <Button size="sm" variant="secondary" onPress={() => router.navigate("/payments")}>
                Upload receipt
              </Button>
            </View>
          ) : null}
        </View>
      </View>
    </View>
  );
}
