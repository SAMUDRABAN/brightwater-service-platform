import Link from "next/link";
import { notFound } from "next/navigation";
import { requireStaff } from "../../../lib/staff";
import { api } from "../../../lib/api";
import { arrivalWindow, gbDate, money, serviceName } from "../../../lib/format";
import { PageHeading, PanelHeading, Status } from "../../../components/Ui";
import { Icon } from "../../../components/Icon";
export const metadata = { title: "Booking details" };
export const dynamic = "force-dynamic";
type Booking = {
  id: string;
  state: string;
  customer_name: string;
  customer_id: string;
  call_id: string | null;
  items: {
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
export default async function BookingPage({ params }: { params: Promise<{ bookingId: string }> }) {
  await requireStaff();
  const { bookingId } = await params;
  if (!/^[a-f0-9-]{36}$/.test(bookingId)) notFound();
  let booking: Booking;
  try {
    booking = await api<Booking>(`/v1/office/bookings/${bookingId}`);
  } catch {
    notFound();
  }
  return (
    <>
      <Link className="back-link" href="/bookings">
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
      {booking.items.map((item, index) => (
        <section className="panel" key={index}>
          <PanelHeading title={serviceName(item.service)} />
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
            <p className="bottom-note">
              Payment is taken by the engineer on the day. Customers book an arrival window, not an
              exact time.
            </p>
          </div>
        </section>
      ))}
      {booking.call_id && (
        <Link href={`/calls/${booking.call_id}`} className="button secondary">
          Open source call record
          <Icon name="arrow" size={15} />
        </Link>
      )}
    </>
  );
}
