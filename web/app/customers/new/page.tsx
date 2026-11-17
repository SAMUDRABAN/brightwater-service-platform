import Link from "next/link";
import { randomUUID } from "node:crypto";
import { redirect } from "next/navigation";
import { createCustomer } from "../../actions";
import { PageHeading, PanelHeading } from "../../../components/Ui";
import { requireStaff } from "../../../lib/staff";

export const metadata = { title: "Add customer" };

export default async function NewCustomer({
  searchParams,
}: {
  searchParams: Promise<{ notice?: string }>;
}) {
  const staff = await requireStaff();
  if (staff.role === "engineer") redirect("/bookings");
  const { notice } = await searchParams;
  return (
    <>
      <Link href="/customers" className="back-link">
        Customers
      </Link>
      <PageHeading
        title="Add customer"
        description="Create a customer record with their first property."
      />
      {notice && (
        <p role="status" className="action-notice">
          {String(notice).slice(0, 220)}
        </p>
      )}
      <section className="panel">
        <PanelHeading title="Customer details" />
        <div className="panel-body">
          <form action={createCustomer} className="stacked-form">
            <input type="hidden" name="request_key" value={randomUUID()} />
            <label>
              Full name{" "}
              <input name="name" minLength={2} maxLength={160} required autoComplete="name" />
            </label>
            <label>
              Customer type
              <select name="kind" defaultValue="homeowner">
                <option value="homeowner">Homeowner</option>
                <option value="landlord">Landlord</option>
              </select>
            </label>
            <label>
              Property address and postcode{" "}
              <textarea name="address" required minLength={6} maxLength={300} rows={3} />
            </label>
            <label>
              UK contact number{" "}
              <input
                name="phone"
                type="tel"
                maxLength={32}
                placeholder="07… or +44…"
                autoComplete="tel"
              />
            </label>
            <label>
              Calling consent reference
              <textarea name="consent_reference" minLength={10} maxLength={300} rows={2} />
              <small>
                Optional. Leave blank to save the number for reference without approving it for
                calls.
              </small>
            </label>
            <label>
              Service reminder
              <select name="service" defaultValue="">
                <option value="">No reminder</option>
                <option value="service">Boiler service</option>
                <option value="cp12">Landlord gas safety certificate</option>
                <option value="combined">Boiler service and gas safety certificate</option>
              </select>
            </label>
            <label>
              Reminder due date <input name="due_date" type="date" />
            </label>
            <label>
              Office notes <textarea name="notes" rows={3} maxLength={1500} />
            </label>
            <div className="customer-actions">
              <button className="button">Save customer</button>
              <Link href="/customers" className="button secondary">
                Cancel
              </Link>
            </div>
          </form>
        </div>
      </section>
    </>
  );
}
