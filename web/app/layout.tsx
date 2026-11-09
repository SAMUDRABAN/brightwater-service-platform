import { currentStaff } from "../lib/staff";
import type { Metadata } from "next";
import Link from "next/link";
import { Navigation } from "./Navigation";
import { SignOut } from "./login/SignOut";
import { Icon } from "../components/Icon";
import "./style.css";
export const metadata: Metadata = {
  title: { default: "Brightwater Office", template: "%s | Brightwater Office" },
  description: "Customer service reminders, follow-ups and the Brightwater diary",
  icons: { icon: "/brand/icon.png" },
};
export default async function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  const user = await currentStaff();
  const initials =
    user?.name
      .split(" ")
      .map((s) => s[0])
      .slice(0, 2)
      .join("")
      .toUpperCase() || "BW";
  return (
    <html lang="en-GB">
      <body>
        <a className="skip" href="#main">
          Skip to content
        </a>
        {user ? (
          <div className="workspace">
            <aside className="sidebar">
              <Link
                href={user.role === "engineer" ? "/bookings" : "/morning"}
                className="brand"
                aria-label="Brightwater office home"
              >
                <img
                  src="/brand/logo.svg"
                  alt="Brightwater Plumbing & Heating"
                  width="187"
                  height="48"
                />
              </Link>
              <div className="workspace-switch">
                <img src="/brand/icon.png" alt="" width="28" height="28" />
                <div>
                  <strong>Brightwater</strong>
                  <small>Office workspace</small>
                </div>
                <span className="workspace-dot" aria-hidden="true" />
              </div>
              <p className="nav-label">Workspace</p>
              <Navigation role={user.role} />
              <div className="sidebar-bottom">
                <div className="sidebar-location">
                  <Icon name="shield" size={16} />
                  <span>Private team workspace</span>
                </div>
                <Link href="/change-password" className="profile-link">
                  <span className="avatar">{initials}</span>
                  <span>
                    <strong>{user.name}</strong>
                    <small>
                      {user.role === "admin"
                        ? "Administrator"
                        : user.role === "engineer"
                          ? "Engineer"
                          : "Office manager"}
                    </small>
                  </span>
                  <Icon name="chevron" size={15} />
                </Link>
                <SignOut />
              </div>
            </aside>
            <div className="content">
              <header className="topbar">
                <div className="breadcrumb">
                  <span>Brightwater</span>
                  <Icon name="chevron" size={13} />
                  <strong>Office</strong>
                </div>
                {user.role !== "engineer" && (
                  <form action="/customers" className="global-search" role="search">
                    <Icon name="search" size={16} />
                    <label className="sr-only" htmlFor="global-search">
                      Search customers
                    </label>
                    <input
                      id="global-search"
                      name="q"
                      placeholder="Search customers…"
                      autoComplete="off"
                      maxLength={100}
                    />
                    <button type="submit" aria-label="Search customers">
                      <Icon name="arrow" size={15} />
                    </button>
                  </form>
                )}
                <span className="office-time">
                  <Icon name="clock" size={14} />
                  UK local time
                </span>
              </header>
              <main id="main">{children}</main>
              <footer className="app-footer">
                <span>Brightwater Plumbing & Heating Ltd</span>
                <span>Fictional assessment workspace</span>
              </footer>
            </div>
          </div>
        ) : (
          <div className="auth-shell">
            <Link href="/login" className="auth-brand">
              <img
                src="/brand/logo.svg"
                alt="Brightwater Plumbing & Heating"
                width="210"
                height="54"
              />
            </Link>
            <main id="main" className="auth-main">
              {children}
            </main>
            <footer className="auth-footer">
              Brightwater Plumbing & Heating Ltd<span>Private office access</span>
            </footer>
          </div>
        )}
      </body>
    </html>
  );
}
