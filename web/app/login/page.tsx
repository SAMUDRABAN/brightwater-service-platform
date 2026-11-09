export const metadata = { title: "Sign in" };
import { signIn } from "./actions";
import { safeReturnPath } from "../../lib/session";
import { Icon } from "../../components/Icon";
export default async function Login({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string; changed?: string }>;
}) {
  const p = await searchParams;
  return (
    <section className="login-panel" aria-labelledby="login-title">
      <div className="login-mark">
        <Icon name="shield" size={24} />
      </div>
      <h1 id="login-title">Welcome back</h1>
      <p className="intro">Sign in to your Brightwater workspace.</p>
      {p.changed && (
        <p role="status" className="action-notice">
          Password saved. Sign in with your new password.
        </p>
      )}
      {p.error && (
        <p className="login-error" role="alert">
          {p.error === "origin"
            ? "Open this sign-in page again, then retry."
            : "Your username or password did not match. Please try again."}
        </p>
      )}
      <form action={signIn} className="login-form">
        <input type="hidden" name="next" value={safeReturnPath(p.next)} />
        <label>
          Username
          <input
            name="username"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            required
            maxLength={80}
          />
        </label>
        <label>
          Password
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={1024}
          />
        </label>
        <button className="button" type="submit">
          Sign in
          <Icon name="arrow" size={16} />
        </button>
      </form>
      <p className="login-help">
        Need access or a password reset?
        <br />
        Contact your Brightwater administrator.
      </p>
      <div className="login-security">
        <Icon name="shield" size={14} />
        <span>Personal access · Automatic sign-out after eight hours</span>
      </div>
    </section>
  );
}
