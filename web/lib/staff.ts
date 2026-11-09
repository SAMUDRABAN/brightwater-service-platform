import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { OFFICE_COOKIE } from "./session";
export type Staff = {
  username: string;
  name: string;
  role: "admin" | "office" | "engineer";
  engineer_id: string | null;
  active: boolean;
  change_required: boolean;
};
export async function staffToken() {
  return (await cookies()).get(OFFICE_COOKIE)?.value;
}
export async function currentStaff(): Promise<Staff | null> {
  const token = await staffToken();
  if (!token) return null;
  let response: Response;
  try {
    response = await fetch(`${process.env.BW_API_URL}/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    return null;
  }
  return response.ok ? response.json() : null;
}
export async function requireStaff(): Promise<Staff> {
  const user = await currentStaff();
  if (!user) redirect("/login");
  if (user.change_required) redirect("/change-password");
  return user;
}
