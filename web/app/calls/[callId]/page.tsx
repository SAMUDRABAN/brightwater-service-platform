export const metadata = { title: "Call record" };
import Link from "next/link";
import { redirect, notFound } from "next/navigation";
import { requireStaff } from "../../../lib/staff";
import { reviewCallOutcome } from "../../actions";
import { api } from "../../../lib/api";
import { duration, gbDate, gbTime, money } from "../../../lib/format";
import { Icon } from "../../../components/Icon";
import { Empty, ErrorState, PageHeading, PanelHeading, Status } from "../../../components/Ui";
export const dynamic = "force-dynamic";
type Detail = {
  id: string;
  customer_id: string;
  customer_name?: string;
  purpose: string;
  state: string;
  attempt: number;
  created_at: string;
  outcome: string | null;
  summary: string;
  media_state: string;
  duration_seconds: number | null;
  events: {
    id: string;
    kind: string;
    occurred_at: string;
    payload: {
      text?: unknown;
      interrupted?: boolean;
      action?: string;
      note?: string;
      actor?: string;
      owner?: string;
      source?: string;
    };
  }[];
  arrangement: {
    status: string;
    saved: boolean;
    total_pence?: number;
    items: {
      property_id: string;
      address: string;
      service: string;
      day: string;
      period: string;
      engineer_name: string | null;
      assignment_changed?: boolean;
    }[];
  };
  bookings: { id: string; state: string; total_pence: number }[];
};
export default async function CallPage({
  params,
  searchParams,
}: {
  params: Promise<{ callId: string }>;
  searchParams: Promise<{ notice?: string }>;
}) {
  const user = await requireStaff();
  if (user.role === "engineer") redirect("/bookings");
  const { callId } = await params;
  if (!/^[a-f0-9-]{36}$/.test(callId)) notFound();
  let call: Detail;
  try {
    call = await api<Detail>(`/v1/calls/${callId}`);
  } catch {
    return <ErrorState href="/calls" />;
  }
  const turns = call.events.filter((e) => ["user_utterance", "agent_utterance"].includes(e.kind));
  const office = call.events.filter((e) => e.kind === "office_followup_updated");
  const review = call.events.find((e) => e.payload.source === "office_outcome_review");
  const { notice } = await searchParams;
  const reviewable =
    !call.outcome &&
    call.purpose !== "browser_simulation" &&
    !call.events.some((e) => e.kind === "recording_refused");
  const completed = ["finished", "failed"].includes(call.state);
  return (
    <>
      <Link href="/calls" className="back-link">
        <Icon name="chevron-left" size={15} />
        Call history
      </Link>
      <PageHeading
        title={call.customer_name || call.customer_id}
        description={`${gbDate(call.created_at, true)} at ${gbTime(call.created_at)} UK · Attempt ${call.attempt}`}
      >
        <Status
          tone={
            call.outcome === "Booked"
              ? "success"
              : call.outcome === "Gas emergency advice"
                ? "emergency"
                : "neutral"
          }
        >
          {call.outcome || (completed ? "Needs review" : "In progress")}
        </Status>
      </PageHeading>
      {notice && <p role="status">{notice}</p>}
      <section className="panel">
        <PanelHeading title="Call summary">
          {call.purpose === "engineering" && (
            <span className="test-label">Engineering roleplay</span>
          )}
        </PanelHeading>
        <div className="panel-body">
          <p>{call.summary || "No staff summary has been recorded yet."}</p>
          {review && (
            <p>
              <strong>Reviewed by {review.payload.actor}</strong> {review.payload.note}
            </p>
          )}
          {reviewable && completed && (
            <form action={reviewCallOutcome} className="controls">
              <input type="hidden" name="call_id" value={call.id} />
              <label htmlFor="review-disposition">Outcome supported by the call evidence</label>
              <select id="review-disposition" name="disposition" required defaultValue="">
                <option value="" disabled>
                  Choose an outcome
                </option>
                <option value="not_available">Not available</option>
                <option value="wrong_number">Wrong number</option>
                <option value="not_interested">Not interested</option>
                <option value="serviced_elsewhere">Serviced elsewhere</option>
                <option value="voicemail">Voicemail</option>
              </select>
              <label htmlFor="review-note">Evidence note</label>
              <textarea id="review-note" name="note" minLength={10} maxLength={1500} required />
              <button className="button" type="submit">
                Save reviewed outcome
              </button>
            </form>
          )}
          {!call.outcome && completed && (
            <p className="muted">
              This attempt has no classified business outcome. It has not been relabelled as a
              booking or an unanswered call.
            </p>
          )}
        </div>
        <dl className="call-detail-summary">
          <div>
            <dt>Customer</dt>
            <dd>
              {call.customer_id.startsWith("BW-") ? (
                <Link href={`/customers/${call.customer_id}`}>{call.customer_id}</Link>
              ) : (
                "Engineering test customer"
              )}
            </dd>
          </div>
          <div>
            <dt>
              {call.purpose === "browser_simulation" ? "Session duration" : "Connected duration"}
            </dt>
            <dd>{duration(call.duration_seconds)}</dd>
          </div>
          <div>
            <dt>Call state</dt>
            <dd>{call.state.replaceAll("_", " ")}</dd>
          </div>
          <div>
            <dt>Type</dt>
            <dd>
              {call.purpose === "browser_simulation"
                ? "Browser test"
                : call.purpose === "engineering"
                  ? "Attended test"
                  : "Customer campaign"}
            </dd>
          </div>
        </dl>
        <div className="call-player">
          <div>
            <strong>Call recording</strong>
            <p>
              {call.media_state === "available"
                ? "Listen to the original conversation before acting on an uncertain detail."
                : `Recording ${call.media_state.replaceAll("_", " ")}. No substitute audio is shown.`}
            </p>
          </div>
          {call.media_state === "available" && (
            <audio
              controls
              preload="none"
              src={`/api/calls/${call.id}/recording`}
              aria-label={`Recording of ${call.customer_name || call.customer_id} call`}
            />
          )}
        </div>
      </section>
      {call.arrangement?.items.length > 0 && (
        <section className="panel">
          <PanelHeading
            title={call.arrangement.saved ? "Confirmed arrangement" : "Selected arrangement"}
          >
            <Status tone={call.arrangement.saved ? "success" : "neutral"}>
              {(
                {
                  prepared: "Awaiting confirmation",
                  expired: "Selection expired",
                  not_booked: "Not booked",
                  confirmed: "Booked",
                  cancelled: "Cancelled",
                } as Record<string, string>
              )[call.arrangement.status] || "Not booked"}
            </Status>
          </PanelHeading>
          <div className="panel-body">
            <p className="muted">
              {call.arrangement.saved
                ? "Saved in the diary. The engineers below are assigned to these visits."
                : "These details were discussed but are not a confirmed reservation. No diary capacity is held."}
            </p>
            {call.arrangement.items.map((item) => (
              <dl className="call-detail-summary" key={item.property_id}>
                <div>
                  <dt>Property</dt>
                  <dd>{item.address}</dd>
                </div>
                <div>
                  <dt>Visit</dt>
                  <dd>
                    {gbDate(item.day + "T12:00:00Z")} ·{" "}
                    {item.period === "MORNING" ? "08:00–12:00" : "12:00–17:00"}
                  </dd>
                </div>
                <div>
                  <dt>{call.arrangement.saved ? "Assigned engineer" : "Proposed engineer"}</dt>
                  <dd>
                    {item.engineer_name || "Needs review"}
                    {item.assignment_changed && " · Diary changed; recheck required"}
                  </dd>
                </div>
                <div>
                  <dt>Service</dt>
                  <dd>
                    {(
                      {
                        service: "Boiler service",
                        cp12: "Gas safety check",
                        combined: "Service and gas safety check",
                      } as Record<string, string>
                    )[item.service] || item.service}
                  </dd>
                </div>
              </dl>
            ))}
            <p>
              <strong>{money(call.arrangement.total_pence || 0)} including VAT</strong>
            </p>
          </div>
        </section>
      )}
      {call.bookings?.length > 0 && (
        <section className="panel">
          <PanelHeading title="Saved bookings" count={call.bookings.length} />
          <div className="panel-body">
            {call.bookings.map((b) => (
              <div className="obligation" key={b.id}>
                <Status tone={b.state === "confirmed" ? "success" : "neutral"}>{b.state}</Status>
                <strong>{money(b.total_pence)} including VAT</strong>
                <Link href={`/bookings/${b.id}`} className="text-link">
                  View diary
                  <Icon name="arrow" size={14} />
                </Link>
              </div>
            ))}
          </div>
        </section>
      )}
      <section className="panel">
        <PanelHeading title="Conversation transcript" count={turns.length}>
          <span className="muted">UK local time</span>
        </PanelHeading>
        {turns.length ? (
          <ol className="transcript">
            {turns.map((e) => (
              <li key={e.id}>
                <div className="transcript-speaker">
                  <span className={`speaker-avatar ${e.kind === "agent_utterance" ? "agent" : ""}`}>
                    {e.kind === "agent_utterance" ? "A" : "C"}
                  </span>
                  <strong>{e.kind === "agent_utterance" ? "Alex" : "Customer"}</strong>
                  {e.payload.interrupted && <span className="test-label">Interrupted</span>}
                  <time dateTime={e.occurred_at}>{gbTime(e.occurred_at)}</time>
                </div>
                <p>
                  {typeof e.payload.text === "string"
                    ? e.payload.text
                    : "Transcript text unavailable"}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <Empty title="No conversation captured" icon="headphones">
            No transcript was captured for this attempt. Its record is still retained.
          </Empty>
        )}
        <div className="panel-footnote">
          <Icon name="file" size={15} />
          <span>
            Transcripts may contain recognition errors. Listen to the recording when a detail is
            uncertain. Timestamps reflect captured call events.
          </span>
        </div>
      </section>
      {office.length > 0 && (
        <section className="panel">
          <PanelHeading title="Office activity" count={office.length} />
          <ul className="access-activity">
            {office.map((e) => (
              <li key={e.id}>
                <span>
                  <strong>
                    {e.payload.action === "resolve"
                      ? "Follow-up completed"
                      : e.payload.action === "reopen"
                        ? "Follow-up reopened"
                        : "Owner updated"}
                  </strong>
                  {e.payload.owner && ` · For ${e.payload.owner}`}
                  <br />
                  {e.payload.note || "No additional note"}
                  <small className="muted"> · {e.payload.actor}</small>
                </span>
                <time dateTime={e.occurred_at}>
                  {gbDate(e.occurred_at)} at {gbTime(e.occurred_at)}
                </time>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
