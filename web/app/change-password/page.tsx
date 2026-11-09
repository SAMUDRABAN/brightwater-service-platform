export const metadata = { title: "Change password" };
import { redirect } from "next/navigation";
import { currentStaff } from "../../lib/staff";
import { changePassword } from "../login/actions";
export default async function PasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const user = await currentStaff();
  if (!user) redirect("/login");
  const { error } = await searchParams;
  return (
    <section className="login-panel">
      <h1>Set your personal password</h1>
      <p>
        Signed in as {user.name}. Choose at least 14 characters. Changing it signs out all your
        sessions.
      </p>
      {error && (
        <p role="alert">
          Passwords must match and your current password must be correct. Choose a new password of
          at least 14 characters.
        </p>
      )}
      <form action={changePassword} className="login-form">
        <p>
          <label>
            Current password
            <input
              name="current_password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={1024}
            />
          </label>
        </p>
        <p>
          <label>
            New password
            <input
              name="new_password"
              type="password"
              autoComplete="new-password"
              required
              minLength={14}
              maxLength={128}
            />
          </label>
        </p>
        <p>
          <label>
            Confirm new password
            <input
              name="confirm_password"
              type="password"
              autoComplete="new-password"
              required
              minLength={14}
              maxLength={128}
            />
          </label>
        </p>
        <button className="button">Save password and sign out</button>
      </form>
    </section>
  );
}
