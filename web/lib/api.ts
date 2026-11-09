import "server-only";
import { staffToken } from "./staff";
export type CallRecord = {
  id: string;
  customer_id: string;
  customer_name: string;
  purpose: string;
  state: string;
  outcome: string | null;
  summary: string | null;
  created_at: string;
  attempt: number;
  duration_seconds: number | null;
  media_state: string;
};
export type Customer = {
  id: string;
  name: string;
  kind: string;
  not_before: string | null;
  contact_blocked: boolean;
  suppressed: boolean;
  destination_approved: boolean;
  next_due: string | null;
  property_count: number;
};
export type Appointment = {
  booking_id: string;
  call_id: string;
  customer_id: string;
  customer_name: string;
  purpose: string;
  created_yesterday: boolean;
  day: string;
  period: string;
  engineer: string;
  address: string;
  service: string;
  state: string;
  price_pence: number;
};
export type Followup = {
  id: string;
  call_id: string;
  customer_id: string;
  customer_name: string;
  owner: string;
  kind: string;
  priority: number;
  detail: string;
  summary: string;
  media_state: string;
  purpose: string;
  resolved: boolean;
  created_at: string;
};
export type DiaryWindow = {
  id: string;
  day: string;
  period: string;
  engineer_id: string;
  engineer: string;
  gas_registered: boolean;
  capacity_minutes: number;
  used_minutes: number;
};
export type Dashboard = {
  environment: string;
  release_id: string;
  dialing_enabled: boolean;
  metrics: {
    customers: number;
    called: number;
    reached: number;
    booked: number;
    still_to_try: number;
    attempts: number;
  };
  followups: Followup[];
  appointments: Appointment[];
  diary: { capacity_minutes: number; used_minutes: number };
  quality: { status: string; voice_score: number | null; conversation_score: number | null };
};
export type CustomerDetail = Customer & {
  notes: string;
  destination_hint: string | null;
  properties: {
    id: string;
    address: string;
    boiler: string;
    boiler_year: number | null;
    obligations: { id: string; service: string; due_date: string; resolved: boolean }[];
  }[];
  calls: CallRecord[];
};
export type CallList = { items: CallRecord[]; total: number; page: number; page_size: number };
export async function api<T>(path: string): Promise<T> {
  const token = await staffToken();
  if (!token) throw new Error("Sign in to the office");
  const response = await fetch(`${process.env.BW_API_URL || "http://127.0.0.1:8787"}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error(`Office service returned ${response.status}`);
  return response.json();
}
