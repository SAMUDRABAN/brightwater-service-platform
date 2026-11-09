"use server";
import { requireStaff, staffToken } from "../../lib/staff";

export async function startManaged(customerId: string, textOnly: boolean) {
  const user = await requireStaff();
  if (user.role !== "admin") return { error: "Administrator access is required." };
  if (!/^BW-\d{4}$/.test(customerId)) return { error: "Choose a fictional assessment customer." };
  try {
    const response = await fetch(`${process.env.BW_API_URL}/v1/managed/sessions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${await staffToken()}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ customer_id: customerId, text_only: textOnly }),
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    const body = await response.json();
    if (!response.ok)
      return {
        error:
          body.error === "managed_busy"
            ? "An evaluation is already active. Finish it or wait four minutes."
            : "The managed candidate is unavailable. No phone call was placed.",
      };
    return {
      token: body.token as string,
      url: body.signed_url as string,
      id: body.id as string,
      customerName: body.customer_name as string,
    };
  } catch {
    return { error: "The evaluation could not be started. No automatic retry was made." };
  }
}

export async function closeManaged(id: string) {
  const user = await requireStaff();
  if (user.role !== "admin" || !/^[a-f0-9-]{36}$/.test(id)) return;
  await fetch(`${process.env.BW_API_URL}/v1/managed/evaluations/${id}/close`, {
    method: "POST",
    headers: { Authorization: `Bearer ${await staffToken()}` },
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  }).catch(() => {});
}
