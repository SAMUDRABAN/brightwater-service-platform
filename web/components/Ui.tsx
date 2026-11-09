import Link from "next/link";
import { Icon, type IconName } from "./Icon";
export function PageHeading({
  title,
  description,
  children,
  eyebrow,
}: {
  title: string;
  description: string;
  children?: React.ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        <p className="intro">{description}</p>
      </div>
      {children && <div className="heading-actions">{children}</div>}
    </div>
  );
}
export function Empty({
  title,
  children,
  icon = "file",
}: {
  title: string;
  children: React.ReactNode;
  icon?: IconName;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name={icon} size={22} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function Status({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "success" | "urgent" | "emergency" | "info";
}) {
  return (
    <span className={`status-badge ${tone}`}>
      <span aria-hidden="true" />
      {children}
    </span>
  );
}
export function PanelHeading({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children?: React.ReactNode;
}) {
  return (
    <div className="panel-heading">
      <h2>
        {title}
        {count !== undefined && <span className="count">{count}</span>}
      </h2>
      {children}
    </div>
  );
}
export function ErrorState({ href = "/morning" }: { href?: string }) {
  return (
    <section className="panel service-error" role="alert">
      <span className="empty-icon">
        <Icon name="alert" />
      </span>
      <h1>We couldn’t load this view</h1>
      <p>Your records are safe. Refresh the page to try the connection again.</p>
      <Link href={href} className="button">
        Try again
      </Link>
    </section>
  );
}
