export const metadata = { title: "Conversation lab" };
import { redirect } from "next/navigation";
import Link from "next/link";
import { api, Customer } from "../../lib/api";
import { requireStaff } from "../../lib/staff";
import ManagedConversation from "./ManagedConversation";
export const dynamic = "force-dynamic";
export default async function ManagedPage() {
  const user = await requireStaff();
  if (user.role !== "admin") redirect("/morning");
  const customers = await api<Customer[]>("/v1/customers");
  let enabled = false;
  let evaluations: {
    id: string;
    customer_id: string;
    state: string;
    outcome: string | null;
    purpose: string;
  }[] = [];
  try {
    enabled = (await api<{ enabled: boolean }>("/v1/managed/status")).enabled;
    if (enabled) evaluations = await api<typeof evaluations>("/v1/managed/evaluations");
  } catch {
    /* Report availability below, keep office navigation usable. */
  }
  return (
    <>
      <p>
        <Link href="/quality">← Conversation quality</Link>
      </p>
      <div className="page-heading">
        <div>
          <h1>Conversation lab</h1>
          <p className="intro">
            Speak with Valory through ElevenLabs using a fictional customer. No telephone call is
            placed.
          </p>
        </div>
        <span className="badge">Engineering evaluation</span>
      </div>
      <section className="panel controls">
        <h2>Listen and check the outcome.</h2>
        <p>
          Voice sessions can save confirmed test bookings in the office diary and appear in Calls as
          browser tests. These bookings use diary capacity. Text sessions use the evaluation diary.
        </p>
        <p>
          Sessions are recorded by ElevenLabs, retained for seven days, and stop within three
          minutes. Use fictional details.
        </p>
        <ManagedConversation
          enabled={enabled}
          customers={customers.map((c) => ({ id: c.id, name: c.name }))}
        />
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Evaluation outcomes</h2>
          <span>Voice and text evaluations</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Customer</th>
                <th>State</th>
                <th>Saved outcome</th>
              </tr>
            </thead>
            <tbody>
              {evaluations.map((e) => (
                <tr key={e.id}>
                  <td>
                    {e.customer_id}
                    <small>
                      {e.purpose === "browser_simulation" ? (
                        <Link href={`/calls/${e.id}`}>View browser test in Calls</Link>
                      ) : (
                        e.id
                      )}
                    </small>
                  </td>
                  <td>{e.state}</td>
                  <td>{e.outcome || "No saved business outcome"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="table-note">
          Refresh after ending a session to see its persisted result. Text results are integration
          evidence, not voice quality scores.
        </p>
      </section>
    </>
  );
}
