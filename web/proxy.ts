import { NextRequest, NextResponse } from "next/server";
import { canonicalOfficeOrigin, localOfficeRequest, OFFICE_COOKIE, safeReturnPath, sessionFormat } from "./lib/session";
export function proxy(request: NextRequest) {
 if (request.nextUrl.pathname === "/login" || sessionFormat(request.cookies.get(OFFICE_COOKIE)?.value)) return NextResponse.next();
 if (request.method !== "GET" || request.nextUrl.pathname.startsWith("/api/")) return new NextResponse("Sign in required", {status: 401});
 const origin = canonicalOfficeOrigin(process.env.BW_WEB_HOST) || (localOfficeRequest(process.env.BW_ENVIRONMENT, request.headers.get("host")) ? `http://${request.headers.get("host")}` : null);
 if (!origin) return new NextResponse("Office address is not configured", {status: 503});
 const url = new URL("/login", origin); url.searchParams.set("next", safeReturnPath(request.nextUrl.pathname));
 return NextResponse.redirect(url);
}
export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico|brand/|fonts/).*)"] };
