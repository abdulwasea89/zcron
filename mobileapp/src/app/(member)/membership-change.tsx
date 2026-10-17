import React, { useState } from "react";
import { View } from "react-native";
import { Text } from "heroui-native";
import { AppScreen } from "@/components/app-screen";
import { SectionCard } from "@/components/section-card";
import { Alert, Badge, Button, Input } from "@/components/ui";
import { EmptyState } from "@/components/empty-state";
import { useGet } from "@/hooks/use-api";
import { api, ApiError } from "@/lib/api";
import { useStripe } from "@stripe/stripe-react-native";

type PlanOption = { id: string; name: string; price: number; currency: string; billing_type: string };
type ChangeRequest = {
  id: string; request_type: string; target_plan_id: string | null; reason: string;
  status: string; save_offer: string | null; created_at: string; reviewed_at: string | null;
  decision_note: string | null; amount_due: number; effective_at: string | null;
  offer_type: string | null; offer_plan_id: string | null; offer_discount_percent: number | null;
};
type ChangeOptions = { current_plan: { id: string; name: string; price: number; currency: string } | null; plans: PlanOption[] };

export default function Screen_membership_change() {
  const options = useGet<ChangeOptions>("/memberships/me/change-options", ["plan.changed", "membership.changed"]);
  const requests = useGet<ChangeRequest[]>("/memberships/me/change-requests", ["membership.changed"]);
  const [selectedPlan, setSelectedPlan] = useState<PlanOption | null>(null);
  const [reason, setReason] = useState("");
  const [cancelReason, setCancelReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { initPaymentSheet, presentPaymentSheet } = useStripe();
  const pending = requests.data?.some((item) => item.status === "pending" || item.status === "offered");

  const submit = async (requestType: string, targetPlanId: string | null, requestReason: string) => {
    setBusy(true); setError(null); setNotice(null);
    try {
      await api.post("/memberships/me/change-requests", {
        request_type: requestType, target_plan_id: targetPlanId, reason: requestReason.trim(),
      });
      setSelectedPlan(null); setReason(""); setCancelReason("");
      setNotice("Request sent. Your current membership remains in place while the gym reviews it.");
      requests.refetch();
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : "Could not send the request.");
    } finally { setBusy(false); }
  };

  const respond = async (request: ChangeRequest, accept: boolean) => {
    setBusy(true); setError(null); setNotice(null);
    try {
      await api.post(`/memberships/me/change-requests/${request.id}/offer-response?accept=${accept}`);
      setNotice(accept ? "Pause accepted. Your membership is now paused." : "Pause declined. Your cancellation is complete.");
      requests.refetch(); options.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not respond to the offer.");
    } finally { setBusy(false); }
  };

  const payUpgrade = async (request: ChangeRequest) => {
    setBusy(true); setError(null); setNotice(null);
    try {
      const checkout = await api.post<{ payment_required: boolean; payment_id: string | null;
        payment_intent_id: string | null; client_secret: string | null; amount: number; currency: string }>(
        `/memberships/me/change-requests/${request.id}/payment-intent`,
      );
      if (checkout.payment_required) {
        if (!checkout.client_secret || !checkout.payment_intent_id) throw new Error("The Stripe payment could not be started.");
        const initialized = await initPaymentSheet({
          paymentIntentClientSecret: checkout.client_secret,
          merchantDisplayName: "Acron membership",
        });
        if (initialized.error) throw new Error(initialized.error.message);
        const presented = await presentPaymentSheet();
        if (presented.error) throw new Error(presented.error.message);
        await api.post(`/memberships/me/change-requests/${request.id}/confirm-payment`, {
          payment_intent_id: checkout.payment_intent_id,
        });
      }
      setNotice("Payment confirmed. Your new plan is active.");
      await Promise.all([requests.refetch(), options.refetch()]);
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : "Could not complete the upgrade payment.");
    } finally { setBusy(false); }
  };

  const currency = options.data?.current_plan?.currency ?? "USD";
  const money = (amount: number, code: string) => `${new Intl.NumberFormat(undefined, { style: "currency", currency: code }).format(amount)}`;

  return (
    <AppScreen title="Membership plan" subtitle="Request a plan change or manage your membership." showBackButton>
      <View className="gap-5">
        {error ? <Alert type="error" message={error} /> : null}
        {notice ? <Alert type="success" message={notice} /> : null}
        <SectionCard title="Current plan">
          {options.loading && !options.data ? <Text type="body-sm" color="muted">Loading your plan…</Text> :
            options.data?.current_plan ? <View className="gap-1">
              <Text type="body-md" className="text-foreground">{options.data.current_plan.name}</Text>
              <Text type="body-sm" color="muted">{money(options.data.current_plan.price, currency)} per billing period</Text>
            </View> : <Text type="body-sm" color="muted">No active plan found.</Text>}
        </SectionCard>

        <SectionCard title="Available plans">
          {options.data?.plans.length ? <View className="gap-2">
            {options.data.plans.map((plan) => {
              const type = plan.price > (options.data?.current_plan?.price ?? 0) ? "upgrade" :
                plan.price < (options.data?.current_plan?.price ?? 0) ? "downgrade" : "transfer";
              const selected = selectedPlan?.id === plan.id;
              return <Button key={plan.id} variant={selected ? "primary" : "secondary"} disabled={busy || pending}
                onPress={() => setSelectedPlan(plan)}>
                {plan.name} · {money(plan.price, plan.currency)} · {type}
              </Button>;
            })}
          </View> : <EmptyState title="No other plans available" message="Ask your gym team if you need a different membership." />}
          {selectedPlan ? <View className="mt-4 gap-3">
            <Input label="Reason" placeholder="Tell us what you need" value={reason} onChangeText={setReason} multiline maxLength={500} />
            <Button loading={busy} disabled={reason.trim().length < 3}
              onPress={() => {
                const current = options.data?.current_plan?.price ?? 0;
                const type = selectedPlan.price > current ? "upgrade" : selectedPlan.price < current ? "downgrade" : "transfer";
                void submit(type, selectedPlan.id, reason);
              }}>Request plan change</Button>
          </View> : null}
        </SectionCard>

        <SectionCard title="Cancel membership">
          <Text type="body-sm" color="muted">Cancellation is reviewed by your gym. They may offer a pause as an alternative.</Text>
          <Input label="Reason" placeholder="Tell us why you want to cancel" value={cancelReason} onChangeText={setCancelReason} multiline maxLength={500} />
          <Button variant="secondary" loading={busy} disabled={busy || pending || cancelReason.trim().length < 3}
            onPress={() => void submit("cancel", null, cancelReason)}>Request cancellation</Button>
        </SectionCard>

        <SectionCard title="Your requests">
          {requests.loading && !requests.data ? <Text type="body-sm" color="muted">Loading requests…</Text> :
            requests.data?.length ? <View className="gap-3">{requests.data.map((request) => <View key={request.id} className="gap-2 rounded-2xl bg-surface p-4">
              <View className="flex-row items-center justify-between gap-3">
                <Text type="body-sm" className="text-foreground">{request.request_type.replace("_", " ")}</Text>
                <Badge tone={request.status === "approved" ? "success" : request.status === "rejected" ? "danger" : "warning"} label={request.status} />
              </View>
              <Text type="body-xs" color="muted">{request.reason}</Text>
              {request.save_offer ? <Text type="body-sm" className="text-foreground">Save offer: {request.save_offer}</Text> : null}
              {request.effective_at ? <Text type="body-xs" color="muted">Effective {new Date(request.effective_at).toLocaleDateString()}</Text> : null}
              {request.status === "payment_pending" ? <Button loading={busy} disabled={busy} onPress={() => void payUpgrade(request)}>
                Pay prorated difference · {money(request.amount_due, currency)}
              </Button> : null}
              {request.decision_note ? <Text type="body-xs" color="muted">Gym note: {request.decision_note}</Text> : null}
              {request.status === "offered" ? <View className="flex-row gap-2">
                <Button disabled={busy} onPress={() => void respond(request, true)}>
                  {request.offer_type === "pause" ? "Accept pause" : "Accept offer"}
                </Button>
                <Button variant="secondary" disabled={busy} onPress={() => void respond(request, false)}>Decline & cancel</Button>
              </View> : null}
            </View>)}</View> : <EmptyState title="No change requests" message="Your plan and cancellation requests will appear here." />}
          {pending ? <Text type="body-xs" color="muted">You can send another request after the current one is resolved.</Text> : null}
        </SectionCard>
      </View>
    </AppScreen>
  );
}
