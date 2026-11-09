"use server";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { OFFICE_COOKIE, safeReturnPath, sameOrigin, SESSION_SECONDS } from "../../lib/session";
import { staffToken } from "../../lib/staff";
async function origin() {
  const h = await headers();
  if (
    !sameOrigin(
      h.get("origin"),
      h.get("x-forwarded-host") || h.get("host"),
      process.env.BW_ENVIRONMENT === "local",
    )
  )
    throw new Error("Invalid form origin");
}
export async function signIn(form: FormData): Promise<void> {
  await origin();
  const response = await fetch(`${process.env.BW_API_URL}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: form.get("username"), password: form.get("password") }),
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) redirect("/login?error=credentials");
  const data = await response.json();
  (await cookies()).set(OFFICE_COOKIE, data.token, {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: SESSION_SECONDS,
  });
  redirect(
    data.user.change_required
      ? "/change-password"
      : data.user.role === "engineer"
        ? "/bookings"
        : safeReturnPath(form.get("next")),
  );
}
export async function signOut(): Promise<void> {
  await origin();
  const token = await staffToken();
  if (token)
    await fetch(`${process.env.BW_API_URL}/v1/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(5000),
    });
  (await cookies()).set(OFFICE_COOKIE, "", {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  redirect("/login");
}
export async function changePassword(form: FormData): Promise<void> {
  await origin();
  const token = await staffToken();
  if (form.get("new_password") !== form.get("confirm_password"))
    redirect("/change-password?error=mismatch");
  const response = await fetch(`${process.env.BW_API_URL}/v1/auth/password`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      current_password: form.get("current_password"),
      new_password: form.get("new_password"),
    }),
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) redirect("/change-password?error=invalid");
  (await cookies()).set(OFFICE_COOKIE, "", {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  redirect("/login?changed=1");
}
