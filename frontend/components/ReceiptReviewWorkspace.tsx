"use client";

import { useEffect, useState } from "react";
import { useRealtimeEvent } from "@/components/Realtime";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Input, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import type { ReceiptReviewItem } from "@/lib/types";

export function ReceiptReviewWorkspace() {
  const [items, setItems] = useState<ReceiptReviewItem[] | null>(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      setItems(await api.get<ReceiptReviewItem[]>("/receipts/review-queue"));
    } catch (e) {
      setError((e as ApiError).message);
      setItems([]);
    }
  }

  useEffect(() => {
    queueMicrotask(() => void load());
  }, []);

  useRealtimeEvent(["receipt.processed", "payment.recorded"], () => void load());

  return (
    <>
      <PageHeader
        title="Receipt review"
        subtitle="Payment screenshots awaiting staff verification against the receiving bank or wallet"
      />

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}

      {items === null ? (
        <Spinner label="Loading receipts..." />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            title="Queue is clear"
            hint="New screenshots appear here. Confirm each transaction in your bank or wallet before approving it."
            icon={
              <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
            }
          />
        </Card>
      ) : (
        <div className="space-y-4">
          {items.map((r) => (
            <ReceiptCard key={r.id} receipt={r} onDone={load} onError={setError} />
          ))}
        </div>
      )}
    </>
  );
}

function confidenceTone(score: number | null): "success" | "warning" | "danger" | "neutral" {
  if (score === null) return "neutral";
  if (score >= 95) return "success";
  if (score >= 70) return "warning";
  return "danger";
}

function ReceiptCard({
  receipt,
  onDone,
  onError,
}: {
  receipt: ReceiptReviewItem;
  onDone: () => void;
  onError: (msg: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [verifiedAmount, setVerifiedAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [settlementConfirmed, setSettlementConfirmed] = useState(false);

  async function review(action: "approve" | "reject" | "request_info") {
    onError("");
    setBusy(true);
    try {
      await api.post(`/receipts/${receipt.id}/review`, {
        action,
        reason: reason || null,
        settlement_confirmed: action === "approve" && settlementConfirmed,
        verified_amount: verifiedAmount ? Number(verifiedAmount) : null,
      });
      onDone();
    } catch (e) {
      onError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title={receipt.member_name || `Member ${receipt.member_id.slice(0, 8)}`}
        subtitle={receipt.extracted_date ? `Dated ${receipt.extracted_date}` : "No date extracted"}
      />
      <div className="grid gap-5 p-6 sm:grid-cols-3">
        <div>
          <div className="text-[10px] font-semibold text-muted-foreground">OCR signal</div>
          <div className="mt-2">
            <Badge tone={confidenceTone(receipt.confidence_score)}>
              {receipt.confidence_score === null ? "—" : `${receipt.confidence_score.toFixed(0)}%`}
            </Badge>
          </div>
        </div>
        <div>
          <div className="text-[10px] font-semibold text-muted-foreground">Amount</div>
          <div className="mt-2 tabular-nums font-medium text-[var(--foreground)]">{receipt.extracted_amount === null ? "—" : money(receipt.extracted_amount)}</div>
        </div>
        <div>
          <div className="text-[10px] font-semibold text-muted-foreground">Payee</div>
          <div className="mt-2 font-medium text-[var(--foreground)]">{receipt.extracted_payee || "—"}</div>
        </div>
        <div>
          <div className="text-[10px] font-semibold text-muted-foreground">Transaction reference</div>
          <div className="mt-2 break-all font-medium text-[var(--foreground)]">{receipt.extracted_txn_id || "—"}</div>
        </div>
        <div>
          <div className="text-[10px] font-semibold text-muted-foreground">Payment method</div>
          <div className="mt-2 font-medium capitalize text-[var(--foreground)]">{receipt.extracted_method?.replaceAll("_", " ") || "—"}</div>
        </div>
        {receipt.is_duplicate && (
          <div className="sm:col-span-3">
            <Badge tone="danger">
              <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" /></svg>
              Possible duplicate
            </Badge>
          </div>
        )}
        {receipt.flags.length > 0 && (
          <div className="sm:col-span-3 flex flex-wrap gap-2">
            {receipt.flags.map((f) => (
              <Badge key={f} tone="warning">{f}</Badge>
            ))}
          </div>
        )}
        {receipt.original_image_url?.startsWith("/receipts/") ? (
          <div className="sm:col-span-3">
            <a
              href={`/api/download${receipt.original_image_url}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--foreground)] hover:underline"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" /></svg>
              View receipt image
            </a>
          </div>
        ) : receipt.original_image_url ? (
          <p className="sm:col-span-3 text-sm text-muted-foreground">
            This older receipt image was not retained and cannot be opened here.
          </p>
        ) : null}
      </div>

      <div className="border-t border-[var(--border)] p-6">
        <label className="mb-4 flex cursor-pointer items-start gap-3 text-sm text-[var(--foreground)]">
          <input
            type="checkbox"
            checked={settlementConfirmed}
            onChange={(event) => setSettlementConfirmed(event.target.checked)}
            className="mt-0.5 accent-[var(--brand)]"
          />
          <span>I verified this transaction in the organization’s bank or wallet and confirmed the funds settled.</span>
        </label>
        {!receipt.plan_id && (
          <div className="mb-4">
            <Input
              label="Amount confirmed in bank or wallet"
              type="number"
              min="0.01"
              max="1000000000"
              step="0.01"
              value={verifiedAmount}
              onChange={(event) => setVerifiedAmount(event.target.value)}
              placeholder="Enter the settled amount"
            />
          </div>
        )}
        <Input
          label="Reason (required to reject / request info)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Optional note for the member"
        />
        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            loading={busy}
            disabled={!settlementConfirmed || (!receipt.plan_id && !(Number(verifiedAmount) > 0))}
            onClick={() => review("approve")}
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            Confirm settlement & approve
          </Button>
          <Button variant="secondary" loading={busy} disabled={!reason} onClick={() => review("request_info")}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" /></svg>
            Request info
          </Button>
          <Button variant="danger" loading={busy} disabled={!reason} onClick={() => review("reject")}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
            Reject
          </Button>
        </div>
      </div>
    </Card>
  );
}
