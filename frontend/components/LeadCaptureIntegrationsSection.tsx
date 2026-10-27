"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Integration = { connected: boolean; webhook_url: string | null; secret: string | null };
type Integrations = { google_ads: Integration; tiktok: Integration };
const EMPTY: Integrations = {
  google_ads: { connected: false, webhook_url: null, secret: null },
  tiktok: { connected: false, webhook_url: null, secret: null },
};

export function LeadCaptureIntegrationsSection() {
  const [items, setItems] = useState<Integrations>(EMPTY);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.get<Integrations>("/leads/capture-integrations")
      .then((data) => { if (active) setItems(data); })
      .catch((error) => { if (active) toast.error((error as ApiError).message || "Could not load lead capture connections."); });
    return () => { active = false; };
  }, []);

  async function connect(provider: keyof Integrations) {
    if (items[provider].connected && !window.confirm("Rotate this secret? The provider must be updated to use the new one.")) return;
    setBusy(provider);
    try {
      const result = await api.put<Integration>(`/leads/capture-integrations/${provider}`, {});
      setItems((current) => ({ ...current, [provider]: result }));
      toast.success(`${provider === "google_ads" ? "Google Ads" : "TikTok relay"} lead capture enabled.`);
    } catch (error) { toast.error((error as ApiError).message || "Could not enable lead capture."); }
    finally { setBusy(null); }
  }

  async function disconnect(provider: keyof Integrations) {
    if (!window.confirm("Disconnect this lead source? New leads from this provider will be rejected.")) return;
    setBusy(provider);
    try {
      await api.del(`/leads/capture-integrations/${provider}`);
      setItems((current) => ({ ...current, [provider]: EMPTY[provider] }));
      toast.success("Lead source disconnected.");
    } catch (error) { toast.error((error as ApiError).message || "Could not disconnect this source."); }
    finally { setBusy(null); }
  }

  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value); toast.success("Copied to clipboard."); }
    catch { toast.error("Could not copy. Select and copy the value manually."); }
  }

  return <div className="mt-6 space-y-4 border-t border-border pt-5">
    <div><h3 className="text-sm font-semibold text-foreground">Ad and external form leads</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">Secure webhooks add new submissions to your Leads pipeline. Intake does not grant marketing consent.</p></div>
    {(["google_ads", "tiktok"] as const).map((provider) => {
      const item = items[provider];
      const title = provider === "google_ads" ? "Google Ads lead forms" : "TikTok / custom form relay";
      return <div key={provider} className="space-y-3 border border-border p-4">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><h4 className="text-sm font-medium text-foreground">{title}</h4><p className="text-xs text-muted-foreground">{item.connected ? "Connected" : "Not connected"}</p></div><div className="flex gap-2"><Button variant="secondary" disabled={busy !== null} onClick={() => void connect(provider)}>{busy === provider ? "Saving…" : item.connected ? "Rotate secret" : "Enable"}</Button>{item.connected && <Button variant="danger" disabled={busy !== null} onClick={() => void disconnect(provider)}>Disconnect</Button>}</div></div>
        {item.connected && item.webhook_url && item.secret && <div className="space-y-2 bg-foreground/[0.035] p-3 text-xs">
          <p className="font-medium text-foreground">Webhook URL</p><p className="break-all font-mono text-[11px] text-muted-foreground">{item.webhook_url}</p><Button variant="secondary" onClick={() => void copy(item.webhook_url!)}>Copy URL</Button>
          <p className="font-medium text-foreground">{provider === "google_ads" ? "Google key" : "Webhook token"}</p><p className="break-all font-mono text-[11px] text-muted-foreground">{item.secret}</p><Button variant="secondary" onClick={() => void copy(item.secret!)}>Copy secret</Button>
          <p className="leading-5 text-muted-foreground">{provider === "google_ads" ? "In Google Ads, set the webhook URL and use this value as the webhook key. Google sends it as google_key." : "Connect TikTok or any external form through a webhook relay (such as Make or Zapier). POST JSON with name, email or phone, and lead_id; send this value in the x-acron-lead-token header. Add source to the JSON to attribute it to an existing lead source; otherwise it is recorded as TikTok. Native TikTok API subscription and lead retrieval need a registered TikTok app and are not configured here."}</p>
        </div>}
      </div>;
    })}
  </div>;
}
