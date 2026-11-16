import Link from "next/link";
import { randomUUID } from "node:crypto";
import { notFound } from "next/navigation";
import { requireStaff } from "../../../lib/staff";
import { api } from "../../../lib/api";
import {
  arrivalWindow,
  bookingTestLabel,
  gbDate,
  gbTime,
  money,
  serviceName,
} from "../../../lib/format";
import { PageHeading, PanelHeading, Status } from "../../../components/Ui";
import { Icon } from "../../../components/Icon";
import { diaryHref } from "../../../lib/office-navigation";
import { updateBooking } from "../../actions";
export const metadata = { title: "Booking details" };
export const dynamic = "force-dynamic";
type Booking = {
  id: string;
  state: string;
  customer_name: string;
  customer_id: string;
  call_id: string | null;
  purpose: string;
  revision: string | null;
  can_cancel: boolean;
  history: { action: string; note: string; actor: string; at: string }[];
  items: {
    id: string;
    rescheduling_options: { id: string; day: string; period: string; engineer: string }[];
    address: string;
    boiler: string;
    service: string;
    day: string;
    period: string;
    engineer: string;
    price_pence: number;
    duration_minutes: number;
    tenant_name: string | null;
    tenant_phone: string | null;
  }[];
};
export default async function BookingPage({
  params,
  searchParams,
}: {
  params: Promise<{ bookingId: string }>;
  searchParams: Promise<{ notice?: string }>;
}) {
  await requireStaff();
  const { bookingId } = await params;
  if (!/^[a-f0-9-]{36}$/.test(bookingId)) notFound();
  let booking: Booking;
  try {
    booking = await api<Booking>(`/v1/office/bookings/${bookingId}`);
  } catch {
    notFound();
  }
  const { notice } = await searchParams;
  const testLabel = bookingTestLabel(booking.purpose, booking.customer_id);
  return (
    <>
      <Link className="back-link" href={diaryHref(booking.items[0].day, booking.purpose)}>
        <Icon name="chevron-left" size={15} />
        Diary & bookings
      </Link>
      <PageHeading
        title={booking.customer_name}
        description="Saved visit details and arrival windows."
      >
        <Status tone={booking.state === "confirmed" ? "success" : "neutral"}>
          {booking.state}
        </Status>
      </PageHeading>
      {notice && (
        <p className="action-notice" role="status">
          {notice.slice(0, 220)}
        </p>
      )}
      {booking.items.map((item) => (
        <section className="panel" key={item.id}>
          <PanelHeading title={serviceName(item.service)}>
            {testLabel && <span className="test-label">{testLabel}</span>}
          </PanelHeading>
          <div className="panel-body">
            <h2>{item.address}</h2>
            <p className="muted">{item.boiler}</p>
            <dl className="fact-list">
              <div>
                <dt>Date</dt>
                <dd>{gbDate(item.day, true)}</dd>
              </div>
              <div>
                <dt>Arrival window</dt>
                <dd>{arrivalWindow(item.period)} UK time</dd>
              </div>
              <div>
                <dt>Engineer</dt>
                <dd>{item.engineer}</dd>
              </div>
              <div>
                <dt>Job length</dt>
                <dd>{item.duration_minutes} minutes</dd>
              </div>
              <div>
                <dt>Price including VAT</dt>
                <dd>{money(item.price_pence)}</dd>
              </div>
              {item.tenant_name && (
                <div>
                  <dt>Tenant / access contact</dt>
                  <dd>
                    {item.tenant_name}
                    {item.tenant_phone && (
                      <>
                        <br />
                        {item.tenant_phone}
                      </>
                    )}
                  </dd>
                </div>
              )}
            </dl>
            <Link href={diaryHref(item.day, booking.purpose)} className="text-link">
              View week in diary <Icon name="arrow" size={14} />
            </Link>
            {booking.revision && item.rescheduling_options.length > 0 && (
              <details className="followup-edit">
                <summary>
                  Reschedule this visit <Icon name="chevron" size={13} />
                </summary>
                <form action={updateBooking} className="workflow-form booking-workflow">
                  <input type="hidden" name="action" value="reschedule" />
                  <input type="hidden" name="booking_id" value={booking.id} />
                  <input type="hidden" name="item_id" value={item.id} />
                  <input type="hidden" name="revision" value={booking.revision} />
                  <input type="hidden" name="request_key" value={randomUUID()} />
                  <label className="wide-field">
                    New arrival window
                    <select name="window_id" required defaultValue="">
                      <option value="" disabled>
                        Choose a window
                      </option>
                      {item.rescheduling_options.map((window) => (
                        <option key={window.id} value={window.id}>
                          {gbDate(window.day, true)} · {arrivalWindow(window.period)} ·{" "}
                          {window.engineer}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="wide-field">
                    Reason for rescheduling
                    <textarea name="note" required maxLength={1500} rows={2} />
                  </label>
                  <div className="form-buttons">
                    <button className="button small">Save new window</button>
                  </div>
                </form>
              </details>
            )}
            <p className="bottom-note">
              Payment is taken by the engineer on the day. Customers book an arrival window, not an
              exact time.
            </p>
          </div>
        </section>
      ))}
      {booking.can_cancel && (
        <section className="panel">
          <PanelHeading title="Cancel booking" />
          <div className="panel-body">
            <details className="followup-edit">
              <summary>
                Cancel all{" "}
                {booking.items.length === 1
                  ? "visits on this booking"
                  : `${booking.items.length} visits`}{" "}
                <Icon name="chevron" size={13} />
              </summary>
              <form action={updateBooking} className="workflow-form booking-workflow">
                <input type="hidden" name="action" value="cancel" />
                <input type="hidden" name="booking_id" value={booking.id} />
                <input type="hidden" name="revision" value={booking.revision || ""} />
                <input type="hidden" name="request_key" value={randomUUID()} />
                <label className="wide-field">
                  Reason for cancellation
                  <textarea name="note" required maxLength={1500} rows={2} />
                </label>
                <label className="confirm-cancellation wide-field">
                  <input type="checkbox" name="confirm_cancel" required />
                  Cancel the booking and release its diary capacity
                </label>
                <div className="form-buttons">
                  <button className="button secondary small">Cancel booking</button>
                </div>
              </form>
            </details>
          </div>
        </section>
      )}
      {booking.history.length > 0 && (
        <section className="panel">
          <PanelHeading title="Booking history" count={booking.history.length} />
          <div className="panel-body">
            {booking.history.map((entry, index) => (
              <p key={index}>
                <strong>
                  {entry.action === "cancel" ? "Cancelled" : "Rescheduled"} by {entry.actor}
                </strong>
                {" · "}
                {gbDate(entry.at, true)} at {gbTime(entry.at)} UK
                <br />
                {entry.note}
              </p>
            ))}
          </div>
        </section>
      )}
      {booking.call_id && (
        <Link href={`/calls/${booking.call_id}`} className="button secondary">
          Open source call record
          <Icon name="arrow" size={15} />
        </Link>
      )}
    </>
  );
}
