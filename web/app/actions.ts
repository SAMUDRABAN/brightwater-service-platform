"use server";

import { staffToken } from "../lib/staff";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { customerIdPattern } from "../lib/customer-id";
import { followupHref } from "../lib/office-navigation";

const messages: Record<string, string> = {
  dialing_disabled: "Calling is disabled in this environment.",
  kill_switch: "New calls are paused.",
  suppressed: "This customer or number is suppressed. No call was queued.",
  fictional_destination: "Assessment sample numbers cannot be approved for calling.",
  invalid_destination: "Enter a valid UK telephone number.",
};

async function post(
  path: string,
  payload: unknown,
  officeWorkflow = false,
): Promise<string | null> {
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
      (officeWorkflow && typeof body.message === "string" ? body.message : null) ||
      "The request was not accepted. Check the record and calling policy before trying again."
    );
  } catch {
    // A timed-out call request may already be queued. Retain the original
    // request key and inspect existing intent rather than claim it failed.
    return "The result could not be confirmed. Check the record before submitting another request.";
  }
}

function value(form: FormData, name: string): string {
  const item = form.get(name);
  return typeof item === "string" ? item.trim() : "";
}

export async function createCustomer(form: FormData) {
  const key = value(form, "request_key");
  if (!/^[a-f0-9-]{36}$/.test(key)) redirect("/customers/new?notice=Invalid%20request");
  const error = await post(
    "/v1/office/customers",
    {
      request_key: key,
      name: value(form, "name"),
      kind: value(form, "kind"),
      address: value(form, "address"),
      phone: value(form, "phone"),
      consent_reference: value(form, "consent_reference"),
      service: value(form, "service") || null,
      due_date: value(form, "due_date") || null,
      notes: value(form, "notes"),
    },
    true,
  );
  if (error) redirect(`/customers/new?notice=${encodeURIComponent(error)}`);
  revalidatePath("/customers");
  redirect(`/customers/BW-C-${key.replaceAll("-", "")}?notice=Customer%20saved`);
}

export async function approveDestination(form: FormData) {
  const customerId = value(form, "customer_id");
  if (!customerIdPattern.test(customerId)) redirect("/customers?notice=Invalid%20customer");
  const error = await post(
    `/v1/customers/${customerId}/destination`,
    {
      phone: value(form, "phone"),
      consent_reference: value(form, "consent_reference"),
    },
    true,
  );
  revalidatePath("/customers");
  redirect(
    `/customers/${customerId}?notice=${encodeURIComponent(error || "Calling number saved.")}#approved-number`,
  );
}

export async function addCustomerReminder(form: FormData) {
  const customerId = value(form, "customer_id");
  if (!customerIdPattern.test(customerId)) redirect("/customers?notice=Invalid%20customer");
  const error = await post(
    `/v1/office/customers/${customerId}/reminders`,
    {
      property_id: value(form, "property_id"),
      service: value(form, "service"),
      due_date: value(form, "due_date"),
    },
    true,
  );
  revalidatePath("/customers");
  redirect(
    `/customers/${customerId}?notice=${encodeURIComponent(error || "Service reminder saved.")}#reminders`,
  );
}

export async function scheduleCustomerCall(form: FormData) {
  const customerId = value(form, "customer_id");
  if (!customerIdPattern.test(customerId)) redirect("/customers?notice=Invalid%20customer");
  const remove = value(form, "mode") === "remove";
  const time = value(form, "schedule_at");
  const error = await post(
    `/v1/office/customers/${customerId}/schedule`,
    {
      schedule_at: remove ? null : time,
    },
    true,
  );
  revalidatePath("/customers");
  const message = error || (remove ? "Scheduled time removed." : "Call schedule saved.");
  redirect(`/customers/${customerId}?notice=${encodeURIComponent(message)}#call-schedule`);
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

export async function requestUKTestCall(form: FormData) {
  const key = value(form, "request_key");
  if (!/^[a-f0-9-]{36}$/.test(key)) redirect("/system?notice=Invalid%20request");
  let callId: string | undefined;
  let notice = "The request could not be confirmed. Check Calls before trying again.";
  try {
    const response = await fetch(`${process.env.BW_API_URL}/v1/uk-tests`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${await staffToken()}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        customer_id: value(form, "customer_id"),
        phone: value(form, "phone"),
        consent: value(form, "consent") === "on",
        request_key: key,
      }),
      cache: "no-store",
      signal: AbortSignal.timeout(18000),
    });
    const result = await response.json();
    if (response.ok && typeof result.id === "string" && /^[a-f0-9-]{36}$/.test(result.id))
      callId = result.id;
    else
      notice = messages[result.error] || result.message || "The UK test request was not accepted.";
  } catch {
    // A timed-out carrier request may have been accepted.
  }
  revalidatePath("/system");
  if (callId) redirect(`/calls/${callId}`);
  redirect(`/system?notice=${encodeURIComponent(notice)}`);
}

export async function updateFollowup(form: FormData) {
  const filters = {
    status: value(form, "view_status"),
    scope: value(form, "view_scope"),
    owner: value(form, "view_owner"),
    q: value(form, "view_q"),
  };
  const id = value(form, "followup_id");
  if (!/^[a-f0-9-]{36}$/.test(id))
    redirect(followupHref({ ...filters, notice: "Invalid follow-up" }));
  const action = value(form, "action");
  const error = await post(
    `/v1/office/followups/${id}`,
    {
      action,
      owner: value(form, "owner") || null,
      note: value(form, "note"),
      request_key: value(form, "request_key"),
    },
    true,
  );
  revalidatePath("/morning");
  revalidatePath("/callbacks");
  revalidatePath(`/calls/${value(form, "call_id")}`);
  const notice =
    error ||
    (action === "resolve"
      ? "Follow-up marked complete."
      : action === "assign"
        ? "Follow-up owner updated."
        : "Follow-up reopened.");
  redirect(followupHref({ ...filters, notice }));
}

export async function updateBooking(form: FormData) {
  const id = value(form, "booking_id");
  if (!/^[a-f0-9-]{36}$/.test(id)) redirect("/bookings");
  const action = value(form, "action");
  if (!value(form, "note") || (action === "cancel" && value(form, "confirm_cancel") !== "on")) {
    redirect(
      `/bookings/${id}?notice=${encodeURIComponent("Enter a reason and confirm the requested change.")}`,
    );
  }
  const error = await post(
    `/v1/office/bookings/${id}`,
    {
      action,
      note: value(form, "note"),
      request_key: value(form, "request_key"),
      revision: value(form, "revision"),
      item_id: value(form, "item_id") || null,
      window_id: value(form, "window_id") || null,
    },
    true,
  );
  revalidatePath("/bookings");
  revalidatePath(`/bookings/${id}`);
  revalidatePath("/morning");
  revalidatePath("/calls", "layout");
  const notice =
    error ||
    (action === "cancel" ? "Booking cancelled. Its capacity is available." : "Visit rescheduled.");
  redirect(`/bookings/${id}?notice=${encodeURIComponent(notice)}`);
}
export async function updatePreferences(form: FormData) {
  const id = value(form, "customer_id");
  if (!customerIdPattern.test(id)) redirect("/customers");
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
