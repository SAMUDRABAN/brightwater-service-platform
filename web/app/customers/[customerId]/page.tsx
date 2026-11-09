export const metadata = { title: "Customer record" };
import Link from "next/link";
import { randomUUID } from "node:crypto";
import { notFound, redirect } from "next/navigation";
import { requireStaff } from "../../../lib/staff";
import { api, type CustomerDetail } from "../../../lib/api";
import { gbDate, serviceName } from "../../../lib/format";
import { approveDestination, requestCall, updatePreferences } from "../../actions";
import { CallTable } from "../../../components/Records";
import { Icon } from "../../../components/Icon";
import { ErrorState, PageHeading, PanelHeading, Status } from "../../../components/Ui";
export const dynamic = "force-dynamic";
export default async function CustomerPage({
  params,
  searchParams,
}: {
  params: Promise<{ customerId: string }>;
  searchParams: Promise<{ notice?: string }>;
}) {
  const user = await requireStaff();
  if (user.role === "engineer") redirect("/bookings");
  const { customerId } = await params;
  if (!/^BW-\d{4}$/.test(customerId)) notFound();
  const { notice } = await searchParams;
  let c: CustomerDetail;
  let calling = false;
  try {
    c = await api<CustomerDetail>(`/v1/office/customers/${customerId}`);
    calling = (await api<{ dialing_enabled: boolean }>("/v1/dashboard")).dialing_enabled;
  } catch {
    return <ErrorState href="/customers" />;
  }
  return (
    <>
      <Link href="/customers" className="back-link">
        <Icon name="chevron-left" size={15} />
        Customers
      </Link>
      {notice && (
        <p role="status" className="action-notice">
          {String(notice).slice(0, 220)}
        </p>
      )}
      <PageHeading
        title={c.name}
        description={`${c.id} · ${c.kind === "landlord" ? "Landlord" : "Homeowner"} · ${c.properties.length} ${c.properties.length === 1 ? "property" : "properties"}`}
      >
        <Status tone={c.suppressed ? "neutral" : c.destination_approved ? "info" : "neutral"}>
          {c.suppressed
            ? "Do not call"
            : c.contact_blocked
              ? "Record needs correction"
              : c.destination_approved
                ? "Number approved"
                : "No calling number approved"}
        </Status>
      </PageHeading>
      <div className="detail-grid">
        <div>
          <section className="panel">
            <PanelHeading title="Properties & reminders" count={c.properties.length} />
            {c.properties.map((property) => (
              <article key={property.id} className="property-row">
                <div className="property-icon">
                  <Icon name="home" size={21} />
                </div>
                <div>
                  <h3>{property.address}</h3>
                  <p>
                    {property.boiler || "Boiler details not recorded"}
                    {property.boiler_year ? ` · Installed ${property.boiler_year}` : ""}
                  </p>
                  {property.obligations.map((o) => (
                    <div className="obligation" key={o.id}>
                      <span>{serviceName(o.service)}</span>
                      <strong>Due {gbDate(o.due_date, true)}</strong>
                      <Status tone={o.resolved ? "success" : "neutral"}>
                        {o.resolved ? "Arranged" : "Reminder due"}
                      </Status>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </section>
          <section className="panel">
            <PanelHeading title="Customer notes" />
            <div className="panel-body">
              <p className="preserve-lines">{c.notes || "No notes recorded."}</p>
              <p className="muted">
                Historic notes provide context. They do not authorise a discount or a change to the
                current booking.
              </p>
            </div>
          </section>
          <section className="panel">
            <PanelHeading title="Call history" count={c.calls.length} />
            <CallTable items={c.calls} />
          </section>
        </div>
        <aside>
          <section className="panel setting-panel">
            <h2>Calling preference</h2>
            <p>
              Customer preferences override the standard calling hours. All times are UK local time.
            </p>
            <form action={updatePreferences} className="stacked-form">
              <input type="hidden" name="customer_id" value={c.id} />
              <label>
                Do not call before
                <input
                  type="time"
                  name="not_before"
                  defaultValue={c.not_before?.slice(0, 5) || ""}
                />
              </label>
              <small>Leave blank to use the standard calling hours.</small>
              <button className="button secondary">Save preference</button>
            </form>
          </section>
          <section className="panel setting-panel">
            <h2>Approved calling number</h2>
            <p>
              {c.destination_hint
                ? `${c.destination_hint}. Approval does not override calling rules or a do-not-call request.`
                : "No separately consented destination has been registered."}
            </p>
            {c.suppressed ? (
              <div className="notice-box">
                <Icon name="shield" />
                <p>
                  This customer is on the do-not-call list. This workspace does not provide an
                  override.
                </p>
              </div>
            ) : (
              <>
                <details className="consent-details">
                  <summary>
                    {c.destination_approved
                      ? "Update approved number"
                      : "Add a consented UK number"}
                  </summary>
                  <form action={approveDestination} className="stacked-form">
                    <input type="hidden" name="customer_id" value={c.id} />
                    <label>
                      Owned or consented UK number
                      <input
                        type="tel"
                        name="phone"
                        placeholder="+44…"
                        pattern="[+]44[1-9][0-9]{8,9}"
                        required
                        maxLength={16}
                        autoComplete="off"
                      />
                    </label>
                    <label>
                      Agreement reference
                      <textarea
                        name="consent_reference"
                        minLength={10}
                        maxLength={300}
                        required
                        rows={3}
                        placeholder="Who agreed to the test, and when"
                      />
                    </label>
                    <button className="button secondary">Save approved number</button>
                  </form>
                </details>
                <form action={requestCall}>
                  <input type="hidden" name="customer_id" value={c.id} />
                  <input
                    type="hidden"
                    name="request_key"
                    value={`office:${c.id}:${randomUUID()}`}
                  />
                  <button
                    className="button full-width"
                    disabled={!calling || !c.destination_approved || c.contact_blocked}
                  >
                    <Icon name="phone" size={15} />
                    Queue a customer call
                  </button>
                </form>
                <small>
                  {calling
                    ? "The admission checks run again before dialling."
                    : "Campaign calling is currently paused."}
                </small>
              </>
            )}
          </section>
        </aside>
      </div>
    </>
  );
}
