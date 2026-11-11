"use server";

import { staffToken } from "../lib/staff";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

const messages: Record<string, string> = {
  dialing_disabled: "Calling is disabled in this environment.",
  kill_switch: "New calls are paused.",
  suppressed: "This customer or number is suppressed. No call was queued.",
  fictional_destination: "Assessment sample numbers cannot be approved for calling.",
  invalid_destination: "Enter an owned or consented UK number in international format.",
};

async function post(path: string, payload: unknown): Promise<string | null> {
  const token = await staffToken();
  if (!token) return "The office connection is not configured.";
  try {
    const response = await fetch(`${process.env.BW_API_URL || "http://127.0.0.1:8787"}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    if (response.ok) return null;
    const body = await response.json();
    return (
      messages[body.error] ||
      "The request was not accepted. Check the record and calling policy before trying again."
    );
  } catch {
    // A timed-out call request may already be queued. Retain the original
    // request key and inspect existing intent rather than claim it failed.
    return "The result could not be confirmed. Check the call record before submitting another request.";
  }
}

function value(form: FormData, name: string): string {
  const item = form.get(name);
  return typeof item === "string" ? item.trim() : "";
}

export async function approveDestination(form: FormData) {
  const customerId = value(form, "customer_id");
  if (!/^BW-\d{4}$/.test(customerId)) redirect("/customers?notice=invalid");
  const error = await post(`/v1/customers/${customerId}/destination`, {
    phone: value(form, "phone"),
    consent_reference: value(form, "consent_reference"),
  });
  revalidatePath("/customers");
  redirect(
    `/customers?notice=${encodeURIComponent(error || "Consented destination saved. Calling checks still apply.")}`,
  );
}

export async function requestCall(form: FormData) {
  const error = await post("/v1/calls", {
    customer_id: value(form, "customer_id"),
    request_key: value(form, "request_key"),
  });
  revalidatePath("/customers");
  redirect(
    `/customers?notice=${encodeURIComponent(error || "Call request queued. Admission checks run again before dialing.")}`,
  );
}

export async function pauseCalling() {
  const error = await post("/v1/control/pause", {});
  revalidatePath("/system");
  revalidatePath("/morning");
  redirect(
    `/system?notice=${encodeURIComponent(error || "New calls are paused. Calls already in progress may continue.")}`,
  );
}

export async function requestEngineeringCall(form: FormData) {
  const requestKey = value(form, "request_key");
  if (!/^[a-f0-9-]{36}$/.test(requestKey)) redirect("/system?notice=Invalid%20request");
  let callId: string | null = null;
  let notice = "The result is uncertain. Check existing call records before another request.";
  try {
    const response = await fetch(`${process.env.BW_API_URL}/v1/engineering/calls`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${await staffToken()}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ request_key: requestKey }),
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    const body = await response.json();
    if (response.ok && typeof body.id === "string" && /^[a-f0-9-]{36}$/.test(body.id))
      callId = body.id;
    else
      notice =
        messages[body.error] ||
        "The attended test was not admitted. Review its configuration or active call.";
  } catch {
    /* Preserve uncertainty; never automatically retry a phone effect. */
  }
  revalidatePath("/system");
  if (callId) redirect(`/calls/${callId}`);
  redirect(`/system?notice=${encodeURIComponent(notice)}`);
}

export async function updateFollowup(form: FormData) {
  const id = value(form, "followup_id");
  if (!/^[a-f0-9-]{36}$/.test(id)) redirect("/callbacks?notice=Invalid%20follow-up");
  const action = value(form, "action");
  const error = await post(`/v1/office/followups/${id}`, {
    action,
    owner: value(form, "owner") || null,
    note: value(form, "note"),
    request_key: value(form, "request_key"),
  });
  revalidatePath("/morning");
  revalidatePath("/callbacks");
  revalidatePath(`/calls/${value(form, "call_id")}`);
  redirect(
    `/callbacks?status=${action === "resolve" ? "resolved" : "open"}&notice=${encodeURIComponent(error || (action === "resolve" ? "Follow-up marked complete." : action === "assign" ? "Follow-up owner updated." : "Follow-up reopened."))}`,
  );
}
export async function updatePreferences(form: FormData) {
  const id = value(form, "customer_id");
  if (!/^BW-\d{4}$/.test(id)) redirect("/customers");
  const error = await post(`/v1/office/customers/${id}/preferences`, {
    not_before: value(form, "not_before") || null,
  });
  revalidatePath("/customers");
  revalidatePath(`/customers/${id}`);
  redirect(`/customers/${id}?notice=${encodeURIComponent(error || "Calling preference saved.")}`);
}

export async function reviewCallOutcome(form: FormData) {
  const id = value(form, "call_id");
  if (!/^[a-f0-9-]{36}$/.test(id)) redirect("/calls");
  const error = await post(`/v1/office/calls/${id}/outcome`, {
    disposition: value(form, "disposition"),
    note: value(form, "note"),
  });
  revalidatePath("/calls");
  revalidatePath("/callbacks");
  revalidatePath("/morning");
  redirect(`/calls/${id}?notice=${encodeURIComponent(error || "Call outcome saved.")}`);
}
