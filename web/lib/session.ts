export const OFFICE_COOKIE = "__Host-brightwater-office";
export const SESSION_SECONDS = 8 * 60 * 60;
export function sessionFormat(value: string | undefined): boolean {
  return !!value && /^bwstaff_[A-Za-z0-9_-]{43}$/.test(value);
}
const OFFICE_PATHS = new Set([
  "/",
  "/morning",
  "/callbacks",
  "/bookings",
  "/customers",
  "/quality",
  "/system",
  "/team",
  "/change-password",
]);
export function safeReturnPath(value: unknown): string {
  if (typeof value !== "string") return "/morning";
  return OFFICE_PATHS.has(value) ||
    /^\/calls\/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value)
    ? value
    : "/morning";
}

export function localOfficeRequest(environment: string | undefined, host: string | null): boolean {
  if (environment !== "local" || !host) return false;
  const match = /^(localhost|127\.0\.0\.1)(?::([1-9][0-9]{0,4}))?$/.exec(host);
  return !!match && (!match[2] || Number(match[2]) <= 65535);
}

export function canonicalOfficeOrigin(publicHost: string | undefined): string | null {
  // This is operator configuration, never an upstream URL or caller Host header.
  if (
    !publicHost ||
    publicHost.length > 253 ||
    !publicHost.includes(".") ||
    publicHost.endsWith(".localhost") ||
    publicHost
      .split(".")
      .some((label) => label.length > 63 || !/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label))
  )
    return null;
  try {
    const origin = new URL(`https://${publicHost}`);
    return origin.hostname === publicHost && origin.host === publicHost ? origin.origin : null;
  } catch {
    return null;
  }
}

export function sameOrigin(origin: string | null, host: string | null, local = false): boolean {
  if (!origin || !host || host.includes(",") || host.includes("/")) return false;
  try {
    const parsed = new URL(origin);
    return (
      parsed.origin === origin &&
      parsed.host === host &&
      (parsed.protocol === "https:" ||
        (local &&
          parsed.protocol === "http:" &&
          ["localhost", "127.0.0.1"].includes(parsed.hostname)))
    );
  } catch {
    return false;
  }
}
