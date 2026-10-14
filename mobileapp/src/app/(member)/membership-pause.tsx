import React, { useState } from "react";
import { View } from "react-native";
import { Text } from "heroui-native";

import { AppScreen } from "@/components/app-screen";
import { SectionCard } from "@/components/section-card";
import { Button, Input, Alert, Badge } from "@/components/ui";
import { Sheet, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { EmptyState } from "@/components/empty-state";
import { useGet } from "@/hooks/use-api";
import { api, ApiError } from "@/lib/api";

type FreezeRequest = {
  id: string;
  reason: string;
  requested_until: string | null;
  source: string;
  status: string;
  created_at: string;
  reviewed_at: string | null;
  decision_note: string | null;
};

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  pending: "warning", approved: "success", rejected: "danger", cancelled: "neutral",
};

export default function Screen_membership_pause() {
  const requests = useGet<FreezeRequest[]>("/memberships/me/freeze-requests");
  const [showForm, setShowForm] = useState(false);
  const [reason, setReason] = useState("");
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const pending = requests.data?.find((item) => item.status === "pending");

  const submit = async () => {
    setBusy(true); setError(null); setNotice(null);
    try {
      let requestedUntil: string | null = null;
      if (until.trim()) {
        const parsedDate = new Date(`${until.trim()}T23:59:59`);
        if (Number.isNaN(parsedDate.getTime())) throw new Error("Enter an end date as YYYY-MM-DD.");
        requestedUntil = parsedDate.toISOString();
      }
      await api.post("/memberships/me/freeze-requests", {
        reason: reason.trim(), requested_until: requestedUntil,
      });
      setShowForm(false); setReason(""); setUntil("");
      setNotice("Your request was sent. Your membership stays active until the gym reviews it.");
      requests.refetch();
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : "Could not send your request.");
    } finally { setBusy(false); }
  };

  const withdraw = async (request: FreezeRequest) => {
    setBusy(true); setError(null); setNotice(null);
    try {
      await api.del(`/memberships/me/freeze-requests/${request.id}`);
      setNotice("Your pending request was withdrawn.");
      requests.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not withdraw your request.");
    } finally { setBusy(false); }
  };

  return (
    <AppScreen title="Pause membership" subtitle="Request a temporary break from your membership." showBackButton>
      <View className="gap-5">
        {error ? <Alert type="error" message={error} /> : null}
        {notice ? <Alert type="success" message={notice} /> : null}

        <SectionCard title="How a pause works">
          <Text type="body-sm" color="muted">
            Tell your gym why you need a break and, if you know it, when you expect to return. A pause only begins after the gym approves it. Your membership time is extended for the approved pause.
          </Text>
        </SectionCard>

        <SectionCard title="Your requests">
          {requests.loading && !requests.data ? <Text type="body-sm" color="muted">Loading requests…</Text> :
            (requests.data ?? []).length === 0 ? <EmptyState title="No pause requests" message="You have not requested a membership pause." /> :
              <View className="gap-3">
                {(requests.data ?? []).map((request) => (
                  <View key={request.id} className="gap-2 rounded-2xl bg-surface p-4">
                    <View className="flex-row items-center justify-between gap-3">
                      <Badge tone={STATUS_TONE[request.status] ?? "neutral"} label={request.status} />
                      <Text type="body-xs" color="muted">{new Date(request.created_at).toLocaleDateString()}</Text>
                    </View>
                    <Text type="body-sm" className="text-foreground">{request.reason}</Text>
                    {request.requested_until ? <Text type="body-xs" color="muted">Requested through {new Date(request.requested_until).toLocaleDateString()}</Text> : null}
                    {request.decision_note ? <Text type="body-xs" color="muted">Gym note: {request.decision_note}</Text> : null}
                    {request.status === "pending" ? <Button variant="secondary" disabled={busy} onPress={() => void withdraw(request)}>Withdraw request</Button> : null}
                  </View>
                ))}
              </View>
          }
        </SectionCard>

        {!pending ? <Button onPress={() => { setError(null); setShowForm(true); }}>Request a pause</Button> : null}
      </View>

      <Sheet isOpen={showForm} onOpenChange={setShowForm}>
        <SheetTitle>Request a pause</SheetTitle>
        <SheetDescription>Your request goes to the gym team for approval. Membership access remains active until then.</SheetDescription>
        <Input
          label="Reason"
          placeholder="Travel, illness, seasonal break…"
          value={reason}
          onChangeText={setReason}
          multiline
          maxLength={500}
          style={{ minHeight: 96, textAlignVertical: "top" }}
        />
        <Input
          label="Expected return date (optional)"
          placeholder="YYYY-MM-DD"
          value={until}
          onChangeText={setUntil}
          keyboardType="numbers-and-punctuation"
          hint="Leave blank if you do not know yet."
        />
        <Button loading={busy} disabled={reason.trim().length < 3} onPress={() => void submit()}>Send request</Button>
        <Button variant="ghost" disabled={busy} onPress={() => setShowForm(false)}>Cancel</Button>
      </Sheet>
    </AppScreen>
  );
}
