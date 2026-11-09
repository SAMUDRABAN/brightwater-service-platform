import { currentStaff } from "../../../../lib/staff";
import { api, type CallList } from "../../../../lib/api";
import { csvRow } from "../../../../lib/csv";
export async function GET(request: Request) {
  const user = await currentStaff();
  if (!user || user.change_required) return new Response("Sign in required", { status: 401 });
  if (user.role === "engineer") return new Response("Not available to this role", { status: 403 });
  const url = new URL(request.url);
  const query = new URLSearchParams({
    page_size: "100",
    scope: ["campaign", "engineering"].includes(url.searchParams.get("scope") || "")
      ? url.searchParams.get("scope")!
      : "all",
    q: (url.searchParams.get("q") || "").slice(0, 100),
    outcome: (url.searchParams.get("outcome") || "").slice(0, 50),
  });
  try {
    const rows = [
      csvRow([
        "Customer ID",
        "Customer name",
        "Call type",
        "Attempt",
        "Started at (UTC)",
        "Duration (seconds)",
        "State",
        "Outcome",
        "Summary",
      ]),
    ];
    let total = 0;
    for (let page = 1; page <= 50; page++) {
      query.set("page", String(page));
      const data = await api<CallList>(`/v1/office/calls?${query}`);
      total = data.total;
      for (const c of data.items)
        rows.push(
          csvRow([
            c.customer_id,
            c.customer_name,
            c.purpose,
            c.attempt,
            new Date(c.created_at).toISOString(),
            c.duration_seconds,
            c.state,
            c.outcome || "Unclassified",
            c.summary,
          ]),
        );
      if (page * 100 >= total) break;
    }
    return new Response("\uFEFF" + rows.join(""), {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="brightwater-call-history-${new Date().toISOString().slice(0, 10)}.csv"`,
        "Cache-Control": "private, no-store",
        "X-Export-Limit": "5000",
        "X-Total-Records": String(total),
      },
    });
  } catch {
    return new Response("The export could not be completed. Please try again.", { status: 503 });
  }
}
