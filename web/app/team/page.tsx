export const metadata = { title: "Team access" };
import { requireStaff, type Staff } from "../../lib/staff";
import { api } from "../../lib/api";
import { redirect } from "next/navigation";
import { updateStaff } from "./actions";
import { gbDate, gbTime } from "../../lib/format";
import { PageHeading, PanelHeading, Status } from "../../components/Ui";
export default async function Team({
  searchParams,
}: {
  searchParams: Promise<{ notice?: string }>;
}) {
  const user = await requireStaff();
  if (user.role !== "admin") redirect("/bookings");
  const team = await api<Staff[]>("/v1/staff");
  const { notice } = await searchParams;
  const events =
    await api<{ id: string; username: string; action: string; created_at: string }[]>(
      "/v1/staff-audit",
    );
  return (
    <>
      <PageHeading
        title="Team access"
        description="Individual accounts and the right access for each person."
      />
      {notice && (
        <p role="status" className="action-notice">
          {notice === "saved"
            ? "Account updated."
            : "The change was not accepted. Check the password and account."}
        </p>
      )}
      <section className="panel team-list">
        <PanelHeading title="Brightwater team" count={team.length}>
          <span className="muted">Administrator access</span>
        </PanelHeading>
        {team.map((member) => (
          <article className="team-member" key={member.username}>
            <div className="team-member-header">
              <span className="avatar">
                {member.name
                  .split(" ")
                  .map((s) => s[0])
                  .slice(0, 2)
                  .join("")}
              </span>
              <div>
                <h2>{member.name}</h2>
                <p>
                  {member.username} ·{" "}
                  {member.role === "admin"
                    ? "Administrator"
                    : member.role === "engineer"
                      ? "Engineer · assigned work only"
                      : "Office team"}
                </p>
                {member.change_required && (
                  <small className="muted">Personal password change required</small>
                )}
              </div>
              <Status tone={member.active ? "info" : "neutral"}>
                {member.active ? "Active" : "Disabled"}
              </Status>
            </div>
            {member.username !== user.username && (
              <details className="followup-edit">
                <summary>Manage access</summary>
                <form action={updateStaff} className="staff-form">
                  <input type="hidden" name="username" value={member.username} />
                  <input type="hidden" name="action" value={member.active ? "disable" : "enable"} />
                  <button className="button secondary">
                    {member.active ? "Disable account" : "Enable account"}
                  </button>
                </form>
                <form action={updateStaff} className="staff-form">
                  <input type="hidden" name="username" value={member.username} />
                  <input type="hidden" name="action" value="reset_password" />
                  <label>
                    New temporary password
                    <input
                      name="temporary_password"
                      type="password"
                      required
                      minLength={14}
                      maxLength={128}
                      autoComplete="new-password"
                    />
                  </label>
                  <button className="button secondary">Reset password</button>
                </form>
              </details>
            )}
          </article>
        ))}
      </section>
      <p className="bottom-note">
        Disabling an account or resetting its password revokes active sessions immediately.
        Engineers can see only their assigned work; Tom is not eligible for gas work.
      </p>
      <section className="panel">
        <PanelHeading title="Recent access activity" />
        <ul className="access-activity">
          {events.map((e) => (
            <li key={e.id}>
              <span>
                <strong>{e.username}</strong> · {e.action.replaceAll("_", " ")}
              </span>
              <time dateTime={e.created_at}>
                {gbDate(e.created_at)} at {gbTime(e.created_at)} UK
              </time>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
