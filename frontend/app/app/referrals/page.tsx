"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/PageHeader";
import { TABLE, THEAD_ROW, TH, TR, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import { ListToolbar } from "@/components/ListToolbar";
import { ListFilterSheet } from "@/components/ListFilterSheet";
import { FieldSelect, NONE } from "@/components/FieldSelect";
import { SelectItem } from "@/components/ui/select";
import { Alert, Button, EmptyState, Input, Spinner } from "@/components/ui";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useModuleGate } from "@/hooks/useModuleGate";
import { api, ApiError } from "@/lib/api";

type Program = { enabled: boolean; reward_description: string };
type Reward = { id: string; recipient_member_id: string; description: string; status: string };
type Referral = {
  id: string;
  referrer_name: string;
  referrer_email: string;
  referred_name: string;
  referred_email: string;
  status: string;
  reward_description: string;
  qualified_at: string | null;
  rewards: Reward[];
};
type Overview = { program: Program; referrals: Referral[]; pending_rewards: number; qualified_count: number };

export default function ReferralsPage() {
  const { ready } = useModuleGate("referrals");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [program, setProgram] = useState<Program>({ enabled: false, reward_description: "A referral reward" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [referralFilter, setReferralFilter] = useState<"all" | "qualified" | "pending">("all");
  const [rewardFilter, setRewardFilter] = useState(NONE);
  const [signupFilter, setSignupFilter] = useState(NONE);
  const [showProgram, setShowProgram] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.get<Overview>("/referrals");
      setOverview(data);
      setProgram(data.program);
    } catch (e) {
      setError((e as ApiError).message);
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  async function saveProgram(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true); setError(""); setNotice("");
    try {
      await api.put<Program>("/referrals/program", program, { "Idempotency-Key": crypto.randomUUID() });
      await load(); setNotice(program.enabled ? "Referral program is live." : "Referral program paused."); setShowProgram(false);
    } catch (e) { setError((e as ApiError).message); }
    finally { setBusy(false); }
  }

  async function fulfill(rewardId: string) {
    setBusy(true); setError(""); setNotice("");
    try {
      await api.post(`/referrals/rewards/${rewardId}/fulfill`, {}, { "Idempotency-Key": crypto.randomUUID() });
      await load(); setNotice("Reward marked as delivered.");
    } catch (e) { setError((e as ApiError).message); }
    finally { setBusy(false); }
  }

  if (!ready) return <div className="p-8"><Spinner /></div>;
  if (overview === null) return error ? <main className="p-8"><Alert tone="danger">{error}</Alert></main> : <div className="p-8"><Spinner /></div>;

  const filteredReferrals = overview.referrals.filter((referral) => {
    const matchesFilter = referralFilter === "all" ||
      (referralFilter === "qualified" ? referral.status === "qualified" : referral.status !== "qualified");
    const matchesReward = rewardFilter === NONE || referral.rewards.some((reward) => reward.status === rewardFilter);
    const matchesSignup = signupFilter === NONE || Boolean(referral.referred_email) === (signupFilter === "complete");
    return matchesFilter && matchesReward && matchesSignup && `${referral.referrer_name} ${referral.referrer_email} ${referral.referred_name} ${referral.referred_email} ${referral.status}`
      .toLowerCase().includes(search.trim().toLowerCase());
  });
  const activeReferralFilterCount = [rewardFilter, signupFilter].filter((v) => v !== NONE).length;
  function clearReferralFilters() { setRewardFilter(NONE); setSignupFilter(NONE); }

  return (
    <main className="w-full">
      <PageHeader title="Referrals" subtitle="Turn happy members into a trackable source of new signups."
        action={<Button onClick={() => setShowProgram(true)}>Program settings</Button>} />
      {error && <Alert tone="danger">{error}</Alert>}
      {notice && <Alert tone="success">{notice}</Alert>}
      <Sheet open={showProgram} onOpenChange={setShowProgram}>
        <SheetContent>
          <SheetHeader><SheetTitle>Program settings</SheetTitle><SheetDescription>Choose the reward and control whether members can share referral codes.</SheetDescription></SheetHeader>
          <SheetBody>
      <form onSubmit={saveProgram} className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><h2 className="font-semibold">Program setup</h2><p className="mt-1 text-sm text-muted-foreground">Each successful referral earns the same reward for the member who invited and the new member. Your team records delivery here.</p></div>
          <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={program.enabled} onChange={(e) => setProgram({ ...program, enabled: e.target.checked })} />Program active</label>
        </div>
        <label className="mt-5 block max-w-xl text-sm font-medium">Reward description<Input className="mt-2" value={program.reward_description} maxLength={200} onChange={(e) => setProgram({ ...program, reward_description: e.target.value })} placeholder="A free class for both members" required minLength={3} /></label>
        <p className="mt-2 text-xs text-muted-foreground">Example: “One free class.” The owner confirms and records when the reward has been delivered.</p>
        <div className="flex justify-end"><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save program"}</Button></div>
      </form>
          </SheetBody>
        </SheetContent>
      </Sheet>

      <ListToolbar
        tabs={[
          { value: "all", label: "All", count: overview.referrals.length },
          { value: "qualified", label: "Qualified", count: overview.qualified_count },
          { value: "pending", label: "Pending", count: overview.referrals.length - overview.qualified_count },
        ]}
        value={referralFilter}
        onChange={setReferralFilter}
        search={search}
        onSearch={setSearch}
        searchPlaceholder="Search referrals…"
        children={(
          <ListFilterSheet title="Filter referrals" description="Find referrals by reward delivery and signup progress." activeCount={activeReferralFilterCount} resultCount={filteredReferrals.length} onClear={clearReferralFilters}>
            <FieldSelect label="Reward delivery" value={rewardFilter} onChange={setRewardFilter}>
              <SelectItem value={NONE}>Any reward status</SelectItem><SelectItem value="pending">Reward pending</SelectItem><SelectItem value="fulfilled">Reward delivered</SelectItem>
            </FieldSelect>
            <FieldSelect label="Signup details" value={signupFilter} onChange={setSignupFilter}>
              <SelectItem value={NONE}>All signups</SelectItem><SelectItem value="complete">Email captured</SelectItem><SelectItem value="incomplete">Signup in progress</SelectItem>
            </FieldSelect>
          </ListFilterSheet>
        )}
      />
      <div className="mt-3 overflow-x-auto">
        <table className={`${TABLE} min-w-[760px]`}>
          <thead><tr className={THEAD_ROW}>
            <th className={`${TH} ${CELL_FIRST}`}>Invited by</th>
            <th className={`${TH} ${CELL}`}>New member</th>
            <th className={`${TH} ${CELL}`}>Status</th>
            <th className={`${TH} ${CELL}`}>Rewards</th>
            <th className={`${TH} ${CELL_LAST}`}>Action</th>
          </tr></thead>
          <tbody>{filteredReferrals.map((referral) => <tr key={referral.id} className={TR}>
            <td className={`${TD} ${CELL_FIRST} py-3`}><p className="text-[13px] font-medium text-foreground">{referral.referrer_name}</p><p className="text-[11px] text-muted-foreground">{referral.referrer_email}</p></td>
            <td className={`${TD} ${CELL} py-3`}><p className="text-[13px] font-medium text-foreground">{referral.referred_name}</p><p className="text-[11px] text-muted-foreground">{referral.referred_email || "Signup started"}</p></td>
            <td className={`${TD} ${CELL} py-3`}><span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-medium ${referral.status === "qualified" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{referral.status === "qualified" ? "Joined and paid" : "Awaiting payment"}</span></td>
            <td className={`${TD} ${CELL} py-3`}><div className="flex flex-wrap gap-2">{referral.rewards.length ? referral.rewards.map((reward) => <span key={reward.id} className="text-[12px] text-muted-foreground">{reward.description} · {reward.status === "fulfilled" ? "Delivered" : "Pending"}</span>) : <span className="text-[12px] text-muted-foreground">Unlocks after payment</span>}</div></td>
            <td className={`${TD} ${CELL_LAST} py-3`}>{referral.rewards.some((reward) => reward.status !== "fulfilled") && <Button type="button" variant="secondary" disabled={busy} onClick={() => { const reward = referral.rewards.find((item) => item.status !== "fulfilled"); if (reward) void fulfill(reward.id); }}>Mark delivered</Button>}</td>
          </tr>)}</tbody>
        </table>
        {filteredReferrals.length === 0 && <EmptyState
          title={overview.referrals.length === 0 ? "No referrals yet" : search || activeReferralFilterCount ? "No matching referrals" : "No referrals in this view"}
          hint={overview.referrals.length === 0 ? "Once the program is active, members can share their referral code from the mobile dashboard." : "Adjust the status, filters, or search and try again."}
        />}
      </div>
    </main>
  );
}
