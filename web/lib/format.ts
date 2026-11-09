export const serviceName = (value: string) =>
  (
    ({
      service: "Boiler service",
      cp12: "Gas safety certificate",
      combined: "Service & certificate",
    }) as Record<string, string>
  )[value] || value.replaceAll("_", " ");
export const followupName = (value: string) =>
  (
    ({
      callback: "Callback",
      urgent: "Urgent callback",
      gas: "Gas emergency",
      gas_emergency: "Gas emergency",
      co_alarm: "CO alarm",
      complaint: "Complaint",
      lead: "Quote enquiry",
      internal_review: "Call review",
    }) as Record<string, string>
  )[value] || value.replaceAll("_", " ");
export const isEmergency = (value: string) => ["gas", "gas_emergency", "co_alarm"].includes(value);
export const gbDate = (value: string, full = false) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: full ? "long" : "short",
    year: full ? "numeric" : undefined,
    timeZone: "Europe/London",
  }).format(new Date(value.length === 10 ? `${value}T12:00:00Z` : value));
export const gbTime = (value: string) =>
  new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/London",
  }).format(new Date(value));
export const money = (pence: number) =>
  new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: pence % 100 ? 2 : 0,
  }).format(pence / 100);
export const duration = (seconds: number | null) => {
  if (seconds == null) return "Not connected";
  const total = Math.round(Math.max(0, seconds));
  return `${Math.floor(total / 60)}m ${(total % 60).toString().padStart(2, "0")}s`;
};
export const arrivalWindow = (period: string) =>
  period === "MORNING" ? "08:00–12:00" : "12:00–17:00";
