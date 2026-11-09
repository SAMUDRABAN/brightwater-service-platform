"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "../components/Icon";
const links: { path: string; label: string; icon: IconName; admin?: boolean }[] = [
  { path: "morning", label: "Overview", icon: "home" },
  { path: "callbacks", label: "Follow-ups", icon: "headphones" },
  { path: "bookings", label: "Diary & bookings", icon: "calendar" },
  { path: "customers", label: "Customers", icon: "users" },
  { path: "calls", label: "Call history", icon: "phone" },
  { path: "quality", label: "Voice & quality", icon: "chart", admin: true },
  { path: "system", label: "Call controls", icon: "settings" },
  { path: "team", label: "Team access", icon: "shield", admin: true },
];
export function Navigation({ role }: { role: string }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main navigation">
      {links
        .filter((l) => (role === "engineer" ? l.path === "bookings" : !l.admin || role === "admin"))
        .map((l) => (
          <Link
            href={`/${l.path}`}
            key={l.path}
            aria-current={
              pathname === `/${l.path}` || pathname.startsWith(`/${l.path}/`) ? "page" : undefined
            }
          >
            <Icon name={l.icon} />
            <span>{l.label}</span>
          </Link>
        ))}
    </nav>
  );
}
