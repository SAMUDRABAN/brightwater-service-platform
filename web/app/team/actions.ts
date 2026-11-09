"use server";
import { requireStaff, staffToken } from "../../lib/staff";
import { headers } from "next/headers";
import { sameOrigin } from "../../lib/session";
import { redirect } from "next/navigation";
export async function updateStaff(form: FormData) {
  const user = await requireStaff();
  if (user.role !== "admin") throw new Error("Administrator required");
  const h = await headers();
  if (
    !sameOrigin(
      h.get("origin"),
      h.get("x-forwarded-host") || h.get("host"),
      process.env.BW_ENVIRONMENT === "local",
    )
  )
    throw new Error("Invalid form origin");
  const username = String(form.get("username"));
  if (!/^[a-z0-9_-]{1,80}$/.test(username)) throw new Error("Invalid username");
  const password = form.get("temporary_password");
  const response = await fetch(`${process.env.BW_API_URL}/v1/staff/${username}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${await staffToken()}`, "Content-Type": "application/json" },
    body: JSON.stringify({ action: form.get("action"), temporary_password: password || undefined }),
    signal: AbortSignal.timeout(10000),
  });
  redirect(`/team?notice=${response.ok ? "saved" : "failed"}`);
}
