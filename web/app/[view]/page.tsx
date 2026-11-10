import { randomUUID } from "node:crypto";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { requireStaff } from "../../lib/staff";
import {
  api,
  type Appointment,
  type CallList,
  type Customer,
  type Dashboard,
  type DiaryWindow,
  type Followup,
} from "../../lib/api";
import { arrivalWindow, gbDate } from "../../lib/format";
import { pauseCalling, requestCall, requestEngineeringCall } from "../actions";
import { BookingTable, CallTable, FollowupList } from "../../components/Records";
import { Empty, ErrorState, PageHeading, PanelHeading, Status } from "../../components/Ui";
import { Icon } from "../../components/Icon";
export const dynamic = "force-dynamic";
type Search = Record<string, string | undefined>;
const titles: Record<string, [string, string]> = {
  morning: [
    "Morning overview",
    "Your priorities, appointments and customer reminders, in one place.",
  ],
  callbacks: [
    "Follow-ups",
    "Everything that needs a person, with the context to pick up the conversation.",
  ],
  bookings: [
    "Diary & bookings",
    "Confirmed visits and available capacity across your engineering team.",
  ],
  customers: ["Customers", "Service reminders, properties and calling preferences."],
  calls: ["Call history", "Every attempt, its outcome and the conversation behind it."],
  quality: ["Voice & quality", "Evidence from real conversations, with the limits made clear."],
  system: ["Call controls", "Manage new calls and check the status of the calling service."],
};
export async function generateMetadata({ params }: { params: Promise<{ view: string }> }) {
  const { view } = await params;
  return { title: titles[view]?.[0] || "Office" };
}
const q = (p: Search, k: string) => String(p[k] || "").slice(0, 100);
const scope = (p: Search) =>
  ["campaign", "engineering"].includes(q(p, "scope")) ? q(p, "scope") : "all";
function Filters({
  children,
  action,
  search = true,
  placeholder = "Search…",
  value = "",
}: {
  children?: React.ReactNode;
  action: string;
  search?: boolean;
  placeholder?: string;
  value?: string;
}) {
  return (
    <form action={action} className="filter-bar">
      {search && (
        <label className="filter-search">
          <Icon name="search" size={17} />
          <span className="sr-only">{placeholder}</span>
          <input name="q" placeholder={placeholder} defaultValue={value} maxLength={100} />
        </label>
      )}
      {children}
      <button className="button secondary small" type="submit">
        <Icon name="filter" size={15} />
        Apply filters
      </button>
      <Link href={action} className="clear-filter">
        Clear
      </Link>
    </form>
  );
}
function ScopeFilter({ value }: { value: string }) {
  return (
    <label className="filter-field">
      <span className="sr-only">Call type</span>
      <select name="scope" defaultValue={value}>
        <option value="all">All call types</option>
        <option value="campaign">Customer campaign</option>
        <option value="engineering">Engineering tests</option>
      </select>
    </label>
  );
}
function CallingStatus({ enabled }: { enabled: boolean }) {
  return (
    <Status tone={enabled ? "success" : "neutral"}>
      {enabled ? "Calling enabled" : "Calling paused"}
    </Status>
  );
}
function CustomerActions({ customer: c, enabled }: { customer: Customer; enabled: boolean }) {
  if (c.suppressed) return <Status>Do not call</Status>;
  if (c.contact_blocked) return <span className="muted">Record needs correction</span>;
  return (
    <div className="customer-actions">
      <form action={requestCall}>
        <input type="hidden" name="customer_id" value={c.id} />
        <input type="hidden" name="request_key" value={`office:${c.id}:${randomUUID()}`} />
        <button
          className="button secondary small"
          disabled={!enabled || !c.destination_approved}
          title={
            !enabled
              ? "Campaign calling is paused"
              : !c.destination_approved
                ? "Approve an owned or consented UK destination first"
                : "Queue one call"
          }
        >
          <Icon name="phone" size={14} />
          Call customer
        </button>
      </form>
    </div>
  );
}
async function Customers({ data, p }: { data: Dashboard; p: Search }) {
  const rows = await api<Customer[]>("/v1/customers");
  const search = q(p, "q").toLocaleLowerCase("en-GB");
  const kind = q(p, "kind");
  const items = rows.filter(
    (c) =>
      (!search || `${c.name} ${c.id}`.toLocaleLowerCase("en-GB").includes(search)) &&
      (!kind || c.kind === kind),
  );
  return (
    <>
      <Filters action="/customers" placeholder="Search by name or customer ID" value={q(p, "q")}>
        <label className="filter-field">
          <span className="sr-only">Customer type</span>
          <select name="kind" defaultValue={kind}>
            <option value="">All customers</option>
            <option value="homeowner">Homeowners</option>
            <option value="landlord">Landlords</option>
          </select>
        </label>
      </Filters>
      <section className="panel">
        <PanelHeading title="Customer directory" count={items.length}>
          <span className="muted">{rows.length} records in this workspace</span>
        </PanelHeading>
        {items.length ? (
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Customer directory">
            <table>
              <caption className="sr-only">Customer directory</caption>
              <thead>
                <tr>
                  <th scope="col">Customer</th>
                  <th scope="col">Properties</th>
                  <th scope="col">Next due</th>
                  <th scope="col">Calling preference</th>
                  <th scope="col">Contact status</th>
                  <th scope="col">Action</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <Link href={`/customers/${c.id}`} className="customer-name">
                        <span className="avatar customer-avatar">
                          {c.name
                            .split(" ")
                            .map((s) => s[0])
                            .slice(0, 2)
                            .join("")}
                        </span>
                        <span>
                          <strong>{c.name}</strong>
                          <small>
                            {c.id} · {c.kind === "landlord" ? "Landlord" : "Homeowner"}
                          </small>
                        </span>
                      </Link>
                    </td>
                    <td>
                      {c.property_count} {c.property_count === 1 ? "property" : "properties"}
                    </td>
                    <td>{c.next_due ? gbDate(c.next_due, true) : "No outstanding reminder"}</td>
                    <td>
                      {c.not_before
                        ? `After ${c.not_before.slice(0, 5)} UK`
                        : "Standard calling hours"}
                    </td>
                    <td>
                      <Status tone={c.destination_approved && !c.suppressed ? "info" : "neutral"}>
                        {c.suppressed
                          ? "Do not call"
                          : c.contact_blocked
                            ? "Needs correction"
                            : c.destination_approved
                              ? "Number approved"
                              : "Not approved for calling"}
                      </Status>
                    </td>
                    <td>
                      <CustomerActions customer={c} enabled={data.dialing_enabled} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No customers found" icon="users">
            Try a different name, customer ID or customer type.
          </Empty>
        )}
        <div className="panel-footnote">
          <Icon name="shield" size={15} />
          <span>
            Assessment phone numbers are blocked. A separately owned or consented UK number is
            required before a campaign call.
          </span>
        </div>
      </section>
    </>
  );
}
async function Calls({ p }: { p: Search }) {
  const page = Math.max(1, Math.min(100000, Number.parseInt(q(p, "page"), 10) || 1));
  const params = new URLSearchParams({
    q: q(p, "q"),
    scope: scope(p),
    page: String(page),
    outcome: q(p, "outcome"),
  });
  const rows = await api<CallList>(`/v1/office/calls?${params}`);
  const pages = Math.max(1, Math.ceil(rows.total / rows.page_size));
  const path = (n: number) =>
    `/calls?${new URLSearchParams({ ...Object.fromEntries(params), page: String(n) })}`;
  return (
    <>
      <Filters action="/calls" placeholder="Search customer, ID or summary" value={q(p, "q")}>
        <ScopeFilter value={scope(p)} />
        <label className="filter-field">
          <span className="sr-only">Outcome</span>
          <select name="outcome" defaultValue={q(p, "outcome")}>
            <option value="">All outcomes</option>
            {[
              "Booked",
              "Callback requested",
              "Urgent callback",
              "Gas emergency advice",
              "Lead",
              "Complaint",
              "Not interested",
              "Serviced elsewhere",
              "Do not call",
              "Wrong number",
              "Not available",
              "Voicemail",
              "No answer",
            ].map((o) => (
              <option key={o}>{o}</option>
            ))}
            <option value="unclassified">Needs review / in progress</option>
          </select>
        </label>
      </Filters>
      <section className="panel">
        <PanelHeading title="Call records" count={rows.total}>
          <a
            className="button secondary small"
            href={`/api/calls/export?${new URLSearchParams({ q: q(p, "q"), scope: scope(p), outcome: q(p, "outcome") })}`}
          >
            <Icon name="file" size={14} />
            Export CSV
          </a>
        </PanelHeading>
        <CallTable items={rows.items} />
        <p className="table-note">CSV exports include up to the latest 5,000 matching records.</p>
        <div className="pagination">
          <span>
            Page {rows.page} of {pages} · {rows.total} records
          </span>
          <div>
            {page > 1 ? (
              <Link href={path(page - 1)} className="button secondary small">
                <Icon name="chevron-left" size={14} />
                Previous
              </Link>
            ) : (
              <span className="pagination-disabled">Previous</span>
            )}
            {page < pages ? (
              <Link href={path(page + 1)} className="button secondary small">
                Next
                <Icon name="chevron" size={14} />
              </Link>
            ) : (
              <span className="pagination-disabled">Next</span>
            )}
          </div>
        </div>
      </section>
    </>
  );
}
async function Followups({ p }: { p: Search }) {
  const status = ["resolved", "all"].includes(q(p, "status")) ? q(p, "status") : "open";
  const rows = await api<Followup[]>(
    `/v1/office/followups?${new URLSearchParams({ status, scope: scope(p) })}`,
  );
  const search = q(p, "q").toLocaleLowerCase("en-GB");
  const items = rows.filter(
    (f) =>
      (!q(p, "owner") || f.owner === q(p, "owner")) &&
      (!search ||
        `${f.customer_name} ${f.summary} ${f.detail}`.toLocaleLowerCase("en-GB").includes(search)),
  );
  return (
    <>
      <div className="page-tabs">
        <Link href="/callbacks" aria-current={status === "open" ? "page" : undefined}>
          Open follow-ups
        </Link>
        <Link
          href="/callbacks?status=resolved"
          aria-current={status === "resolved" ? "page" : undefined}
        >
          Completed
        </Link>
        <Link href="/callbacks?status=all" aria-current={status === "all" ? "page" : undefined}>
          All follow-ups
        </Link>
      </div>
      <Filters action="/callbacks" placeholder="Search name or follow-up details" value={q(p, "q")}>
        <input type="hidden" name="status" value={status} />
        <ScopeFilter value={scope(p)} />
        <label className="filter-field">
          <span className="sr-only">Assigned to</span>
          <select name="owner" defaultValue={q(p, "owner")}>
            <option value="">Everyone</option>
            <option>Sarah</option>
            <option>Mark</option>
          </select>
        </label>
      </Filters>
      <FollowupList items={items} />
      <p className="bottom-note">
        Marking a follow-up complete closes the office task. It does not change the call outcome or
        cancel a booking.
      </p>
    </>
  );
}
async function Diary({ data, p }: { data: Dashboard; p: Search }) {
  const windows = await api<DiaryWindow[]>("/v1/office/diary");
  const dates = [...new Set(windows.map((w) => w.day))].sort();
  const start = dates.includes(q(p, "week")) ? q(p, "week") : dates[0];
  const end = start ? new Date(`${start}T12:00:00Z`) : null;
  if (end) end.setUTCDate(end.getUTCDate() + 7);
  const endDay = end?.toISOString().slice(0, 10) || "";
  const engineers = [...new Set(windows.map((w) => w.engineer))];
  const chosen = q(p, "engineer");
  const current = windows.filter(
    (w) =>
      (!start || w.day >= start) &&
      (!endDay || w.day < endDay) &&
      (!chosen || w.engineer === chosen),
  );
  const appointments = data.appointments.filter(
    (a) =>
      (!chosen || a.engineer === chosen) &&
      (!start || a.day >= start) &&
      (!endDay || a.day < endDay),
  );
  const weekStarts = dates.filter((_, i) => i % 5 === 0);
  const slotCount = Math.max(
    1,
    ...[...new Set(current.map((w) => w.day))].map(
      (day) => current.filter((w) => w.day === day).length,
    ),
  );
  const total = current.reduce((a, w) => a + w.capacity_minutes, 0);
  const used = current.reduce((a, w) => a + w.used_minutes, 0);
  return (
    <>
      <Filters action="/bookings" search={false}>
        <label className="filter-field">
          <span className="sr-only">Week commencing</span>
          <select name="week" defaultValue={start}>
            {weekStarts.map((d) => (
              <option key={d} value={d}>
                Week of {gbDate(d)}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-field">
          <span className="sr-only">Engineer</span>
          <select name="engineer" defaultValue={chosen}>
            <option value="">All assigned engineers</option>
            {engineers.map((e) => (
              <option key={e}>{e}</option>
            ))}
          </select>
        </label>
      </Filters>
      <div className="diary-summary">
        <div>
          <Icon name="calendar" />
          <span>
            <strong>{appointments.length}</strong> confirmed visits this week
          </span>
        </div>
        <div>
          <span className="legend-dot available" />
          <span>{Math.max(0, total - used) / 60} hours available</span>
        </div>
        <div>
          <span className="legend-dot occupied" />
          <span>Booked and pre-existing work</span>
        </div>
      </div>
      <section className="panel">
        <PanelHeading title="Weekly capacity">
          <span className="muted">Morning 08:00–12:00 · Afternoon 12:00–17:00</span>
        </PanelHeading>
        {current.length ? (
          <div
            className="diary-grid"
            tabIndex={0}
            role="region"
            aria-label="Weekly diary; scroll horizontally for later days"
            style={{ gridTemplateRows: `auto repeat(${slotCount}, auto)` }}
          >
            {[...new Set(current.map((w) => w.day))].map((day) => (
              <div className="diary-day" key={day} style={{ gridRow: `span ${slotCount + 1}` }}>
                <div className="diary-day-heading">
                  <span>
                    {new Intl.DateTimeFormat("en-GB", {
                      weekday: "short",
                      timeZone: "Europe/London",
                    }).format(new Date(`${day}T12:00:00Z`))}
                  </span>
                  <strong>{gbDate(day)}</strong>
                </div>
                {current
                  .filter((w) => w.day === day)
                  .map((w) => (
                    <div className="diary-window" key={w.id}>
                      <div>
                        <strong>{w.engineer.split(" ")[0]}</strong>
                        <span>{w.period === "MORNING" ? "Morning" : "Afternoon"}</span>
                      </div>
                      <div className="capacity">
                        <span
                          style={{
                            width: `${Math.min(100, (w.used_minutes / w.capacity_minutes) * 100)}%`,
                          }}
                        />
                      </div>
                      <small>
                        {w.gas_registered
                          ? `${(w.capacity_minutes - w.used_minutes) / 60}h available`
                          : "Plumbing work only"}
                      </small>
                      {appointments
                        .filter(
                          (a) =>
                            a.day === w.day && a.period === w.period && a.engineer === w.engineer,
                        )
                        .map((a) => (
                          <Link
                            key={`${a.booking_id}-${a.address}`}
                            className="diary-appointment"
                            href={`/bookings/${a.booking_id}`}
                          >
                            {a.customer_name}
                            <small>
                              {a.service === "cp12"
                                ? "Gas safety check"
                                : a.service === "combined"
                                  ? "Combined visit"
                                  : "Boiler service"}
                            </small>
                          </Link>
                        ))}
                    </div>
                  ))}
              </div>
            ))}
          </div>
        ) : (
          <Empty title="No diary windows available" icon="calendar">
            There are no windows for the selected engineer and week.
          </Empty>
        )}
      </section>
      <BookingTable items={appointments} />
      <p className="bottom-note">
        Gas work is assigned only to Dan and Priya. Each has up to three hours of jobs per window.
        Payment is taken by the engineer; prices include VAT.
      </p>
    </>
  );
}
function Quality() {
  return (
    <>
      <section className="voice-hero">
        <div className="voice-orb">
          <Icon name="headphones" size={32} />
        </div>
        <div>
          <Status tone="info">Selected voice</Status>
          <h2>Valory</h2>
          <p>British English · ElevenLabs v4 Turbo</p>
          <span className="muted">
            The selected calling voice. Listening scores are not inferred from a voice sample.
          </span>
        </div>
        <Link href="/managed" className="button secondary">
          Open conversation lab
          <Icon name="arrow" size={15} />
        </Link>
      </section>
      <section className="panel">
        <PanelHeading title="Voice sample">
          <span className="muted">Generated audio, not a customer call</span>
        </PanelHeading>
        <div className="audio-sample">
          <div>
            <strong>Valory through a phone codec</strong>
            <p>The same short service-booking script used in the voice comparison.</p>
          </div>
          <audio
            controls
            preload="none"
            src="/voice-auditions/valory-phone.wav"
            aria-label="Valory phone-codec audition"
          />
        </div>
      </section>
      <section className="panel">
        <PanelHeading title="Quality scorecard">
          <Status>Not independently measured</Status>
        </PanelHeading>
        <div className="scorecard">
          {[
            ["Voice quality", "35%", "Naturalness, clarity, pronunciation and pace."],
            ["Conversation quality", "35%", "Listening, interruptions and keeping the thread."],
            ["Task correctness", "15%", "Accurate details and authorised actions."],
            ["Reliability", "10%", "Deployed operation and failure recovery."],
            ["Running cost", "5%", "The cost of a useful completed contact."],
          ].map(([name, weight, detail]) => (
            <div key={name}>
              <div>
                <strong>{name}</strong>
                <p>{detail}</p>
              </div>
              <span>{weight}</span>
              <Status>Not measured</Status>
            </div>
          ))}
        </div>
      </section>
      <div className="notice-box">
        <Icon name="file" />
        <p>
          Attended engineering calls are retained in{" "}
          <Link href="/calls?scope=engineering">call history</Link>. Saved outcomes and recordings
          are evidence of those calls; they are not an independent listening study or proof of UK
          production readiness.
        </p>
      </div>
    </>
  );
}
async function Controls({ data, admin }: { data: Dashboard; admin: boolean }) {
  const campaign = await api<{
    enabled: boolean;
    due_customers: number;
    landlords_due: number;
    blockers: string[];
  }>("/v1/campaign/status");
  const engineering = admin
    ? await api<{
        enabled: boolean;
        recipient: string;
        remaining: number;
        active: boolean;
        duration_limit_seconds: number;
      }>("/v1/engineering/status")
    : null;
  return (
    <>
      <div className="settings-grid">
        <section className="panel setting-panel">
          <div className="setting-icon">
            <Icon name="phone" size={23} />
          </div>
          <h2>Customer campaign</h2>
          <CallingStatus enabled={data.dialing_enabled} />
          <p>
            Every call checks UK calling hours, the customer’s preferences, consent and the
            do-not-call list.
          </p>
          <dl className="fact-list">
            <div>
              <dt>Weekdays</dt>
              <dd>10:00–19:30</dd>
            </div>
            <div>
              <dt>Saturday</dt>
              <dd>10:00–13:00</dd>
            </div>
            <div>
              <dt>Sunday</dt>
              <dd>No calls</dd>
            </div>
            <div>
              <dt>Retry limit</dt>
              <dd>Three attempts, at least a day apart</dd>
            </div>
          </dl>
          <p>
            <strong>{campaign.due_customers}</strong> customers due in the next 28 days, including{" "}
            {campaign.landlords_due} landlords. The scheduler prioritises landlords and checks every
            destination again before dialing.
          </p>
          {campaign.blockers.length > 0 && (
            <div className="panel-body">
              <strong>Before automatic calling</strong>
              <ul>
                {campaign.blockers.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="muted">
            Uses the ElevenLabs caller. Tenant numbers are collected for access and are never
            dialed.
          </p>
          <form action={pauseCalling}>
            <button className="button secondary" type="submit">
              Pause new calls
            </button>
          </form>
          <small>
            Pausing also disables attended test admission. Calls already in progress may continue.
          </small>
        </section>
        {engineering && (
          <section className="panel setting-panel">
            <div className="setting-icon">
              <Icon name="headphones" size={23} />
            </div>
            <h2>Attended phone test</h2>
            <Status>{engineering.remaining} requests remaining</Status>
            <p>
              Calls only your privately approved test phone, {engineering.recipient}. Uses fictional
              customer, property and diary details.
            </p>
            <dl className="fact-list">
              <div>
                <dt>Maximum duration</dt>
                <dd>{Math.round(engineering.duration_limit_seconds / 60)} minutes</dd>
              </div>
              <div>
                <dt>Concurrent calls</dt>
                <dd>One</dd>
              </div>
              <div>
                <dt>Current call</dt>
                <dd>{engineering.active ? "Active or awaiting review" : "None"}</dd>
              </div>
            </dl>
            <form action={requestEngineeringCall}>
              <input type="hidden" name="request_key" value={randomUUID()} />
              <button
                className="button"
                disabled={!engineering.enabled || engineering.active || engineering.remaining === 0}
              >
                <Icon name="phone" size={16} />
                Call my test phone
              </button>
            </form>
            <small>
              Keep your phone ready. An uncertain request must be reviewed before trying again. UK
              campaign calling remains separate.
            </small>
          </section>
        )}
      </div>
      <section className="panel">
        <PanelHeading title="Workspace details" />
        <dl className="fact-list workspace-details">
          <div>
            <dt>Environment</dt>
            <dd>{data.environment}</dd>
          </div>
          <div>
            <dt>Release</dt>
            <dd>
              <code>{data.release_id.slice(0, 12)}</code>
            </dd>
          </div>
          <div>
            <dt>Assessment data</dt>
            <dd>Eight fictional customer records</dd>
          </div>
          <div>
            <dt>Access</dt>
            <dd>Individual staff accounts with role permissions</dd>
          </div>
        </dl>
      </section>
    </>
  );
}
export default async function View({
  params,
  searchParams,
}: {
  params: Promise<{ view: string }>;
  searchParams: Promise<Search>;
}) {
  const { view } = await params;
  const p = await searchParams;
  if (!titles[view]) notFound();
  const user = await requireStaff();
  if (user.role === "engineer" && view !== "bookings") redirect("/bookings");
  if (user.role === "office" && view === "quality") redirect("/morning");
  try {
    const data = await api<Dashboard>("/v1/dashboard");
    const [title, description] = titles[view];
    let body: React.ReactNode;
    if (view === "morning") {
      const followups = await api<Followup[]>("/v1/office/followups");
      const m = data.metrics;
      const urgent = followups.filter((f) => f.priority === 0).length;
      const capacity = Math.max(0, data.diary.capacity_minutes - data.diary.used_minutes);
      body = (
        <>
          <div className="section-label">
            <h2>Campaign at a glance</h2>
            <span>Customer campaign only</span>
          </div>
          <div className="metrics">
            {[
              ["Customers called", m.called, "phone"],
              ["Conversations", m.reached, "users"],
              ["Customers booked", m.booked, "calendar"],
              ["Still to try", m.still_to_try, "clock"],
            ].map(([label, value, icon]) => (
              <div className="metric" key={label}>
                <div>
                  <span>{label}</span>
                  <Icon name={icon as "phone"} />
                </div>
                <strong>{value}</strong>
                <small>
                  {label === "Still to try"
                    ? `Of ${m.customers} customers`
                    : label === "Customers called"
                      ? `${m.attempts} call attempts`
                      : label === "Conversations"
                        ? "Named customer reached"
                        : "Confirmed in the diary"}
                </small>
              </div>
            ))}
          </div>
          <div className="morning-grid">
            <div>
              <FollowupList items={followups.slice(0, 5)} compact />
              <BookingTable
                items={data.appointments.filter((a) => a.created_yesterday)}
                title="Booked yesterday"
                compact
              />
            </div>
            <aside className="overview-aside">
              <section className="panel day-priorities">
                <div className="mini-icon">
                  <Icon name="headphones" size={21} />
                </div>
                <h2>Today’s priorities</h2>
                <div className="priority-number">
                  <strong>{followups.length}</strong>
                  <span>open follow-ups</span>
                </div>
                <p>
                  {urgent
                    ? `${urgent} urgent ${urgent === 1 ? "item needs" : "items need"} your attention first.`
                    : "No urgent items are waiting."}
                </p>
                <Link href="/callbacks" className="button secondary full-width">
                  Open follow-up list
                  <Icon name="arrow" size={15} />
                </Link>
              </section>
              <section className="panel capacity-panel">
                <div className="inline-title">
                  <Icon name="calendar" />
                  <h2>Diary capacity</h2>
                </div>
                <strong className="capacity-number">
                  {capacity / 60}
                  <span>hours available</span>
                </strong>
                <div className="capacity">
                  <span
                    style={{
                      width: `${data.diary.capacity_minutes ? Math.min(100, (data.diary.used_minutes / data.diary.capacity_minutes) * 100) : 0}%`,
                    }}
                  />
                </div>
                <p>Across the supplied three-week diary. Includes existing blocked work.</p>
                <Link href="/bookings" className="text-link">
                  View the diary
                  <Icon name="arrow" size={14} />
                </Link>
              </section>
              <div className="quiet-note">
                <Icon name="shield" size={17} />
                <p>
                  Engineering tests are labelled in the work queue and excluded from campaign
                  totals.
                </p>
              </div>
            </aside>
          </div>
        </>
      );
    } else if (view === "callbacks") body = await Followups({ p });
    else if (view === "customers") body = await Customers({ data, p });
    else if (view === "calls") body = await Calls({ p });
    else if (view === "bookings") body = await Diary({ data, p });
    else if (view === "quality") body = <Quality />;
    else body = await Controls({ data, admin: user.role === "admin" });
    return (
      <>
        {p.notice && (
          <div className="action-notice" role="status">
            <Icon name="file" size={17} />
            {String(p.notice).slice(0, 220)}
          </div>
        )}
        <PageHeading
          title={user.role === "engineer" ? "Your assigned diary" : title}
          description={
            user.role === "engineer"
              ? `${user.name}, here are your visits and available arrival windows.`
              : description
          }
          eyebrow={
            view === "morning"
              ? new Intl.DateTimeFormat("en-GB", {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                  timeZone: "Europe/London",
                }).format(new Date())
              : undefined
          }
        >
          {user.role !== "engineer" && <CallingStatus enabled={data.dialing_enabled} />}
        </PageHeading>
        {body}
      </>
    );
  } catch {
    return <ErrorState href={`/${view}`} />;
  }
}
