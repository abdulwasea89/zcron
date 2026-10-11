"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Alert, Button, EmptyState, Input, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type TrialSlot = {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string | null;
  remaining_capacity: number;
};

type LeadBooking = {
  id: string;
  booking_type: "trial" | "tour";
  class_title: string | null;
  starts_at: string;
  ends_at: string | null;
  status: "scheduled" | "attended" | "no_show" | "cancelled";
  notes: string | null;
};

type Props = {
  leadId: string;
  preferredTimes: string | null;
  onLeadChanged: () => Promise<void>;
};

const STATUS_STYLE: Record<LeadBooking["status"], string> = {
  scheduled: "bg-amber-50 text-amber-700",
  attended: "bg-emerald-50 text-emerald-700",
  no_show: "bg-rose-50 text-rose-700",
  cancelled: "bg-zinc-100 text-zinc-600",
};

export function LeadBookings({ leadId, preferredTimes, onLeadChanged }: Props) {
  const [bookings, setBookings] = useState<LeadBooking[] | null>(null);
  const [slots, setSlots] = useState<TrialSlot[]>([]);
  const [bookingType, setBookingType] = useState<"trial" | "tour">("trial");
  const [slotId, setSlotId] = useState("");
  const [tourTime, setTourTime] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const [bookingRows, slotRows] = await Promise.all([
        api.get<LeadBooking[]>(`/leads/${leadId}/bookings`),
        api.get<TrialSlot[]>("/leads/trial-slots"),
      ]);
      setBookings(bookingRows);
      setSlots(slotRows);
      setSlotId((current) => current || slotRows[0]?.id || "");
    } catch (caught) {
      setError((caught as ApiError).message);
      setBookings([]);
    }
  }, [leadId]);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  async function createBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = bookingType === "trial"
        ? { booking_type: "trial", class_session_id: slotId, notes }
        : { booking_type: "tour", starts_at: new Date(tourTime).toISOString(), notes };
      await api.post(`/leads/${leadId}/bookings`, payload, {
        "Idempotency-Key": crypto.randomUUID(),
      });
      setNotes("");
      setTourTime("");
      setNotice(bookingType === "trial" ? "Trial class booked." : "Gym tour booked.");
      await Promise.all([load(), onLeadChanged()]);
    } catch (caught) {
      setError((caught as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(bookingId: string, status: "attended" | "no_show" | "cancelled") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.patch(`/leads/${leadId}/bookings/${bookingId}`, { status }, {
        "Idempotency-Key": crypto.randomUUID(),
      });
      setNotice(status === "attended" ? "Visit recorded." : status === "no_show" ? "No-show recorded." : "Booking cancelled.");
      await Promise.all([load(), onLeadChanged()]);
    } catch (caught) {
      setError((caught as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  const hasActiveBooking = bookings?.some((booking) => booking.status === "scheduled") ?? false;

  return (
    <section className="mb-6 rounded-xl border border-border bg-muted/20 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Trial or gym tour</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {preferredTimes ? `Preferred times: ${preferredTimes}` : "Reserve a class trial or schedule a private tour."}
          </p>
        </div>
        {bookings === null && <Spinner />}
      </div>

      {error && <div className="mt-3"><Alert tone="danger">{error}</Alert></div>}
      {notice && <div role="status" className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{notice}</div>}

      {!hasActiveBooking && (
        <form onSubmit={createBooking} className="mt-4 grid gap-3 rounded-lg border border-border bg-card p-3 sm:grid-cols-[130px_minmax(0,1fr)_auto]">
          <select
            aria-label="Booking type"
            value={bookingType}
            onChange={(event) => setBookingType(event.target.value as "trial" | "tour")}
            className="h-10 rounded-md border border-foreground/15 bg-background px-3 text-sm"
          >
            <option value="trial">Class trial</option>
            <option value="tour">Gym tour</option>
          </select>
          {bookingType === "trial" ? (
            <select
              aria-label="Available trial class"
              value={slotId}
              onChange={(event) => setSlotId(event.target.value)}
              required
              className="h-10 min-w-0 rounded-md border border-foreground/15 bg-background px-3 text-sm"
            >
              {slots.length === 0 && <option value="">No available classes</option>}
              {slots.map((slot) => (
                <option key={slot.id} value={slot.id}>
                  {slot.title} · {new Date(slot.starts_at).toLocaleString()} · {slot.remaining_capacity} spots
                </option>
              ))}
            </select>
          ) : (
            <Input aria-label="Tour date and time" type="datetime-local" value={tourTime} onChange={(event) => setTourTime(event.target.value)} required />
          )}
          <Button type="submit" disabled={busy || (bookingType === "trial" && !slotId)} loading={busy}>Book</Button>
          <textarea
            aria-label="Booking notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            maxLength={2000}
            placeholder="Optional preparation or accessibility notes"
            className="min-h-20 rounded-md border border-foreground/15 bg-background px-3 py-2 text-sm sm:col-span-3"
          />
        </form>
      )}

      <div className="mt-4 space-y-2">
        {bookings?.length === 0 ? (
          <EmptyState title="No trial or tour booked" hint="Choose an available class or schedule a gym tour." />
        ) : bookings?.map((booking) => (
          <article key={booking.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{booking.class_title || (booking.booking_type === "tour" ? "Gym tour" : "Trial")}</span>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_STYLE[booking.status]}`}>
                  {booking.status.replace("_", " ")}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{new Date(booking.starts_at).toLocaleString()}</p>
              {booking.notes && <p className="mt-1 text-xs text-muted-foreground">{booking.notes}</p>}
            </div>
            {booking.status === "scheduled" && (
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="secondary" disabled={busy} onClick={() => void changeStatus(booking.id, "attended")}>Attended</Button>
                <Button type="button" variant="ghost" disabled={busy} onClick={() => void changeStatus(booking.id, "no_show")}>No-show</Button>
                <Button type="button" variant="danger" disabled={busy} onClick={() => void changeStatus(booking.id, "cancelled")}>Cancel</Button>
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
