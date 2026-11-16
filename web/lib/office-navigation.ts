export const callScopes = {
  all: "All call types",
  campaign: "Customer campaign",
  uk_test: "UK test",
  engineering: "Engineering test",
  browser_simulation: "Browser test",
} as const;

export type CallScope = keyof typeof callScopes;

export function callScope(value: string, fallback: CallScope = "all"): CallScope {
  return Object.hasOwn(callScopes, value) ? (value as CallScope) : fallback;
}

export function followupHref({
  status,
  scope,
  owner,
  q,
  notice,
}: {
  status?: string;
  scope?: string;
  owner?: string;
  q?: string;
  notice?: string;
}) {
  const params = new URLSearchParams({
    status: status === "resolved" || status === "all" ? status : "open",
    scope: callScope(scope || "", "campaign"),
  });
  if (owner === "Sarah" || owner === "Mark") params.set("owner", owner);
  if (q) params.set("q", q.slice(0, 100));
  if (notice) params.set("notice", notice);
  return `/callbacks?${params}`;
}

export function weekStart(day: string) {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
  return date.toISOString().slice(0, 10);
}

export function diaryHref(day: string, scope?: string) {
  const params = new URLSearchParams({ week: weekStart(day) });
  if (scope) params.set("scope", callScope(scope));
  return `/bookings?${params}`;
}
