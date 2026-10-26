"use client";

import { useEffect, useState, useCallback } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, EmptyState, Input, Select, Spinner } from "@/components/ui";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Section, SectionBody, SubHeading } from "@/components/settings/primitives";
import { api, ApiError } from "@/lib/api";
import { useRealtimeEvent } from "@/components/Realtime";
import type { AuditLogOut, AuditLogPage, AuditActionGroup } from "@/lib/types";

const PAGE_SIZE = 50;

function formatTime(iso: string): string {
  const d = new Date(iso + "Z");
  return d.toLocaleString();
}

function actionColor(action: string): "info" | "success" | "warning" | "neutral" {
  if (action.startsWith("auth.") || action.startsWith("mfa.")) return "info";
  if (action.startsWith("payment.") || action.startsWith("cash.")) return "success";
  if (action.startsWith("plan.") || action.startsWith("class.")) return "warning";
  return "neutral";
}

function actionShort(action: string): string {
  return action.split(".").pop()?.replace(/_/g, " ") ?? action;
}

export function AuditWorkspace({ embedded = false }: { embedded?: boolean }) {
  const [logs, setLogs] = useState<AuditLogOut[] | null>(null);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");

  // Filters
  const [search, setSearch] = useState("");
  const [actionDomain, setActionDomain] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [entityType, setEntityType] = useState("");

  // Dropdown data
  const [actionGroups, setActionGroups] = useState<AuditActionGroup[]>([]);
  const [entityTypes, setEntityTypes] = useState<string[]>([]);

  const load = useCallback(async (p: number) => {
    setError("");
    setLogs(null);
    const params = new URLSearchParams();
    params.set("page", String(p));
    params.set("page_size", String(PAGE_SIZE));
    if (search) params.set("search", search);
    if (actionFilter) params.set("action", actionFilter);
    if (entityType) params.set("entity_type", entityType);
    try {
      const result = await api.get<AuditLogPage>(`/audit?${params}`);
      setLogs(result.items);
      setTotal(result.total);
      setTotalPages(result.total_pages);
      setPage(result.page);
    } catch (e) {
      setError((e as ApiError).message);
      setLogs([]);
    }
  }, [search, actionFilter, entityType]);

  useEffect(() => { queueMicrotask(() => void load(1)); }, [load]);

  const loadMeta = useCallback(async () => {
    try {
      const groups = await api.get<AuditActionGroup[]>("/audit/actions");
      setActionGroups(groups);
      const types = new Set<string>();
      for (const g of groups) {
        for (const a of g.actions) {
          const parts = a.split(".");
          if (parts.length > 1) types.add(parts[0]);
        }
      }
      setEntityTypes(Array.from(types).sort());
    } catch {
      // best-effort
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void loadMeta()); }, [loadMeta]);

  useRealtimeEvent(["audit.*"], () => load(page));

  const availableActions = actionDomain
    ? actionGroups.find((g) => g.domain === actionDomain)?.actions ?? []
    : [];

  function handleSearch() { load(1); }

  function handleResetFilters() {
    setSearch("");
    setActionDomain("");
    setActionFilter("");
    setEntityType("");
  }

  function handleDomainChange(domain: string) {
    setActionDomain(domain);
    setActionFilter("");
  }

  const hasFilters = search || actionFilter || entityType;

  const body = (
    <>
      <div className="py-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="min-w-[200px] flex-1">
            <Input
              placeholder="Search actions, entities, IDs…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSearch(); }}
              size="sm"
            />
          </div>
          <div className="w-40">
            <Select aria-label="Domain" value={actionDomain} onChange={(e) => handleDomainChange(e.target.value)} size="sm">
              <option value="">All domains</option>
              {actionGroups.map((g) => (
                <option key={g.domain} value={g.domain}>{g.domain}</option>
              ))}
            </Select>
          </div>
          <div className="w-48">
            <Select aria-label="Action" value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} size="sm">
              <option value="">All actions</option>
              {availableActions.map((a) => (
                <option key={a} value={a}>{actionShort(a)}</option>
              ))}
            </Select>
          </div>
          <div className="w-36">
            <Select aria-label="Entity" value={entityType} onChange={(e) => setEntityType(e.target.value)} size="sm">
              <option value="">All entities</option>
              {entityTypes.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </Select>
          </div>
          <Button onClick={handleSearch}>Search</Button>
          {hasFilters && <Button variant="ghost" onClick={handleResetFilters}>Clear</Button>}
        </div>
      </div>

      <div className="py-4">
        <div className="flex items-baseline justify-between gap-3">
          <SubHeading>Events</SubHeading>
          {logs && (
            <span className="text-[12px] text-muted-foreground">
              {total} result{total === 1 ? "" : "s"}
            </span>
          )}
        </div>

        <div className="mt-3 border border-foreground/10 bg-card">
          {logs === null ? (
            <Spinner label="Loading audit log..." />
          ) : logs.length === 0 ? (
            <EmptyState
              title="No events found"
              hint={hasFilters ? "Try adjusting your filters." : "No audit events recorded yet. Events appear as you use the platform."}
              action={hasFilters ? <Button variant="ghost" onClick={handleResetFilters}>Clear filters</Button> : undefined}
            />
          ) : (
            <>
              <div className="flex items-center gap-4 border-b border-foreground/10 px-5 py-2.5 font-mono text-[10px] font-medium uppercase tracking-widest text-[var(--muted-foreground)]">
                <span className="w-32 shrink-0">Time</span>
                <span className="flex-1">Action</span>
                <span className="flex-1">Actor</span>
                <span className="flex-1">Entity</span>
              </div>
              <Accordion multiple key={page + actionFilter + search + entityType}>
                {logs.map((log) => (
                  <AccordionItem key={log.id} value={log.id}>
                    <AccordionTrigger>
                      <div className="flex flex-1 items-center gap-4 min-w-0">
                        <span className="w-32 shrink-0 text-xs text-[var(--foreground-muted)] tabular-nums">
                          {formatTime(log.created_at)}
                        </span>
                        <span className="flex-1 min-w-0">
                          <Badge tone={actionColor(log.action)}>{actionShort(log.action)}</Badge>
                        </span>
                        <span className="flex-1 min-w-0 truncate text-[var(--foreground-muted)]">
                          {log.actor_name || log.actor_email || log.actor_user_id || "System"}
                        </span>
                        <span className="flex-1 min-w-0 truncate text-[var(--foreground-muted)]">
                          {log.entity_type ? `${log.entity_type}` : "—"}
                          {log.entity_id && (
                            <span className="ml-1.5 font-mono text-[10px] text-[var(--muted)]">{log.entity_id.slice(0, 8)}…</span>
                          )}
                        </span>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="space-y-4">
                        <div className="flex flex-wrap gap-6">
                          <JsonBlock label="Old values" data={log.old_values} />
                          <JsonBlock label="New values" data={log.new_values} />
                          <JsonBlock label="Metadata" data={log.metadata} />
                        </div>
                        {log.ip_address && (
                          <p className="text-xs text-[var(--muted)]">
                            <span className="font-medium text-[var(--foreground-muted)]">IP address:</span> {log.ip_address}
                          </p>
                        )}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
            </>
          )}
        </div>

        {totalPages > 1 && (
          <div className="mt-3 flex items-center justify-between">
            <p className="text-xs text-[var(--foreground-muted)]">
              Page {page} of {totalPages}
            </p>
            <div className="flex gap-2">
              <Button variant="ghost" disabled={page <= 1} onClick={() => load(page - 1)}>Previous</Button>
              <Button variant="ghost" disabled={page >= totalPages} onClick={() => load(page + 1)}>Next</Button>
            </div>
          </div>
        )}
      </div>
    </>
  );

  if (embedded) {
    return (
      <>
        {error && <div className="mb-4"><Alert>{error}</Alert></div>}
        <Section id="audit" title="Audit log" description="Full searchable trail of every state change">
          {body}
        </Section>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Audit Log"
        subtitle="Full searchable trail of every state change in your organization"
      />
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      <SectionBody>{body}</SectionBody>
    </>
  );
}

function JsonBlock({ label, data }: { label: string; data: Record<string, unknown> | null }) {
  if (!data || Object.keys(data).length === 0) return null;
  return (
    <div className="min-w-0 flex-1">
      <p className="mb-1 text-[10px] font-semibold text-muted-foreground">{label}</p>
      <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-lg border border-[var(--border)] bg-[var(--surface)] p-2 font-mono text-[10px] text-[var(--foreground)]">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
