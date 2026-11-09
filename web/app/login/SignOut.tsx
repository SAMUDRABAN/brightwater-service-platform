"use client";
import { usePathname } from "next/navigation";
import { signOut } from "./actions";

export function SignOut() {
  const pathname = usePathname();
  if (pathname === "/login") return null;
  return (
    <form action={signOut} className="signout">
      <button type="submit">Sign out</button>
    </form>
  );
}
