import Link from "next/link";
import { randomUUID } from "node:crypto";
import type { Appointment, CallRecord, Followup } from "../lib/api";
import {
  arrivalWindow,
  duration,
  followupName,
  gbDate,
  gbTime,
  isEmergency,
  money,
  serviceName,
} from "../lib/format";
import { updateFollowup } from "../app/actions";
import { Icon } from "./Icon";
import { Empty, PanelHeading, Status } from "./Ui";
export function FollowupList({ items, compact = false }: { items: Followup[]; compact?: boolean }) {
  return (
    <section className="panel">
      <PanelHeading
        title={compact ? "Your follow-up queue" : "Follow-up list"}
        count={items.length}
      >
        {compact ? (
          <Link href="/callbacks" className="text-link">
            View all
            <Icon name="arrow" size={15} />
          </Link>
        ) : (
          <span className="muted">Priority order</span>
        )}
      </PanelHeading>
      {items.length ? (
        <div className="followups">
          {items.map((f) => (
            <article key={f.id} className={`followup ${isEmergency(f.kind) ? "emergency" : ""}`}>
              <div
                className={`followup-mark ${isEmergency(f.kind) ? "emergency" : f.priority === 0 ? "urgent" : ""}`}
              >
                <Icon
                  name={
                    isEmergency(f.kind) || f.priority === 0
                      ? "alert"
                      : f.kind === "complaint"
                        ? "file"
                        : "phone"
                  }
                  size={18}
                />
              </div>
              <div className="followup-body">
                <div className="record-kicker">
                  <Status
                    tone={
                      isEmergency(f.kind) ? "emergency" : f.priority === 0 ? "urgent" : "neutral"
                    }
                  >
                    {followupName(f.kind)}
                  </Status>
                  {f.purpose === "browser_simulation" && (
                    <span className="test-label">Browser test</span>
                  )}
                  {f.purpose === "engineering" && (
                    <span className="test-label">Engineering test</span>
                  )}
                </div>
                <h3>
                  <Link href={`/calls/${f.call_id}`}>{f.customer_name}</Link>
                </h3>
                <p>{f.summary || f.detail}</p>
                <div className="record-meta">
                  <span>For {f.owner}</span>
                  {f.created_at && <span>{gbDate(f.created_at)}</span>}
                  <span>
                    <Icon name="headphones" size={13} />
                    {f.media_state === "available"
                      ? "Recording available"
                      : "Recording unavailable"}
                  </span>
                </div>
                {!compact && (
                  <details className="followup-edit">
                    <summary>
                      Manage follow-up
                      <Icon name="chevron" size={13} />
                    </summary>
                    <form action={updateFollowup} className="workflow-form">
                      <input type="hidden" name="followup_id" value={f.id} />
                      <input type="hidden" name="call_id" value={f.call_id} />
                      <input type="hidden" name="request_key" value={randomUUID()} />
                      <label>
                        Assigned to
                        <select name="owner" defaultValue={f.owner}>
                          {f.kind !== "complaint" && <option>Sarah</option>}
                          <option>Mark</option>
                        </select>
                      </label>
                      <label className="wide-field">
                        Completion or handover note
                        <textarea
                          name="note"
                          rows={2}
                          maxLength={1500}
                          placeholder="Add the context your colleague needs"
                        />
                      </label>
                      <div className="form-buttons">
                        <button
                          name="action"
                          value={f.resolved ? "reopen" : "resolve"}
                          className="button small"
                        >
                          <Icon name={f.resolved ? "arrow" : "check"} size={15} />
                          {f.resolved ? "Reopen follow-up" : "Mark complete"}
                        </button>
                        <button name="action" value="assign" className="button secondary small">
                          Save owner
                        </button>
                      </div>
                    </form>
                  </details>
                )}
              </div>
              <Link
                href={`/calls/${f.call_id}`}
                className="record-open"
                aria-label={`Open ${f.customer_name} call record`}
              >
                <Icon name="chevron" size={18} />
              </Link>
            </article>
          ))}
        </div>
      ) : (
        <Empty title="You’re all caught up" icon="check">
          No follow-ups match this view. Customer requests that need a person will appear here with
          their call summary and recording.
        </Empty>
      )}
    </section>
  );
}
export function BookingTable({
  items,
  title = "Confirmed bookings",
  compact = false,
}: {
  items: Appointment[];
  title?: string;
  compact?: boolean;
}) {
  return (
    <section className="panel">
      <PanelHeading title={title} count={items.length}>
        {compact ? (
          <Link href="/bookings" className="text-link">
            Open diary
            <Icon name="arrow" size={15} />
          </Link>
        ) : (
          <span className="muted">Arrival windows, UK time</span>
        )}
      </PanelHeading>
      {items.length ? (
        <div className="table-wrap" tabIndex={0} role="region" aria-label={title}>
          <table>
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr>
                <th scope="col">Customer & property</th>
                <th scope="col">Appointment</th>
                <th scope="col">Engineer</th>
                <th scope="col">Service</th>
                {!compact && <th scope="col">Price</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((a, i) => (
                <tr key={`${a.booking_id}-${i}`}>
                  <td>
                    <strong>{a.customer_name || a.address}</strong>
                    <small>{a.address}</small>
                    {a.purpose === "browser_simulation" && (
                      <span className="test-label">Browser test</span>
                    )}
                    {a.purpose === "engineering" && (
                      <span className="test-label">Engineering test</span>
                    )}
                  </td>
                  <td>
                    <strong>{gbDate(a.day)}</strong>
                    <small>{arrivalWindow(a.period)}</small>
                  </td>
                  <td>
                    <span className="engineer-name">
                      <span className="avatar tiny">
                        {a.engineer
                          .split(" ")
                          .map((s) => s[0])
                          .join("")}
                      </span>
                      {a.engineer}
                    </span>
                  </td>
                  <td>
                    {serviceName(a.service)}
                    {a.call_id && (
                      <small>
                        <Link href={`/bookings/${a.booking_id}`}>View booking record</Link>
                      </small>
                    )}
                  </td>
                  {!compact && (
                    <td className="numeric">
                      <strong>{money(a.price_pence)}</strong>
                      <small>Including VAT</small>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          title={compact ? "No bookings made yesterday" : "No bookings match this view"}
          icon="calendar"
        >
          Confirmed appointments will appear here with their engineer and arrival window. Try
          changing the filters to see other bookings.
        </Empty>
      )}
    </section>
  );
}
export function CallTable({ items }: { items: CallRecord[] }) {
  return items.length ? (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Call history">
      <table>
        <caption className="sr-only">Call history</caption>
        <thead>
          <tr>
            <th scope="col">Customer</th>
            <th scope="col">Date & time</th>
            <th scope="col">Outcome</th>
            <th scope="col">Duration</th>
            <th scope="col">Record</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id}>
              <td>
                <Link className="record-title" href={`/calls/${c.id}`}>
                  {c.customer_name || c.customer_id}
                </Link>
                <small>
                  {c.customer_id} · Attempt {c.attempt}
                </small>
                {c.purpose === "browser_simulation" && (
                  <span className="test-label">Browser test</span>
                )}
                {c.purpose === "engineering" && (
                  <span className="test-label">Engineering test</span>
                )}
              </td>
              <td>
                {gbDate(c.created_at)}
                <small>{gbTime(c.created_at)} UK</small>
              </td>
              <td>
                <Status
                  tone={
                    c.outcome === "Booked"
                      ? "success"
                      : c.outcome === "Gas emergency advice"
                        ? "emergency"
                        : "neutral"
                  }
                >
                  {c.outcome ||
                    (c.state === "finished" || c.state === "failed"
                      ? "Needs review"
                      : "In progress")}
                </Status>
              </td>
              <td className="numeric">{duration(c.duration_seconds)}</td>
              <td>
                <Link href={`/calls/${c.id}`} className="text-link">
                  View record
                  <Icon name="arrow" size={14} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <Empty title="No calls match this view" icon="phone">
      Change the search or filters to find a call. Every admitted attempt is retained, including
      failed and unanswered calls.
    </Empty>
  );
}
