"use client";

import dynamic from "next/dynamic";
import type { CSSProperties } from "react";
import { Button, Spinner } from "@/components/ui";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { DashboardWork } from "@/lib/dashboard-work";

const loading = () => <Spinner label="Loading work…" />;
const ReceiptReview = dynamic(() => import("./ReceiptReviewWorkspace").then((module) => module.ReceiptReviewWorkspace), { loading });
const Approvals = dynamic(() => import("./MemberApprovalsWorkspace").then((module) => module.MemberApprovalsWorkspace), { loading });
const Leads = dynamic(() => import("./LeadWorkspace").then((module) => module.LeadWorkspace), { loading });
const Tasks = dynamic(() => import("./TasksWorkspace").then((module) => module.TasksWorkspace), { loading });
const RetentionCases = dynamic(() => import("./RetentionCasesPanel").then((module) => module.RetentionCasesPanel), { loading });

export function DashboardWorkSheet({ work, onClose }: { work: DashboardWork | null; onClose: () => void }) {
  return <Sheet open={Boolean(work)} onOpenChange={(open) => { if (!open) onClose(); }}>
    <SheetContent style={{ "--sheet-max-w": "1040px" } as CSSProperties}>
      <SheetHeader><SheetTitle>{work?.title ?? "Daily priority"}</SheetTitle><SheetDescription>Complete the work here, then return to your daily priorities.</SheetDescription></SheetHeader>
      <SheetBody>{work && <div key={`${work.kind}:${work.taskId ?? work.memberId ?? "queue"}`}>
        {work.kind === "receipts" ? <ReceiptReview /> : work.kind === "approvals" ? <Approvals />
          : work.kind === "leads" ? <Leads untouchedOnly /> : work.kind === "tasks" ? <Tasks initialEditId={work.taskId} />
            : <RetentionCases focusMemberId={work.memberId} />}
      </div>}</SheetBody>
      <SheetFooter><Button variant="secondary" onClick={onClose}>Back to dashboard</Button></SheetFooter>
    </SheetContent>
  </Sheet>;
}
