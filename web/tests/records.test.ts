import { callScope, diaryHref, followupHref, weekStart } from "../lib/office-navigation.ts";
import test from "node:test";
import assert from "node:assert/strict";
import { csvCell, csvRow } from "../lib/csv.ts";
import {
  arrivalWindow,
  bookingTestLabel,
  duration,
  gbDate,
  gbTime,
  isEmergency,
  money,
} from "../lib/format.ts";
test("CSV quotes caller content and preserves multiline cells", () => {
  assert.equal(
    csvRow(["A, B", 'he said "yes"', "line one\nline two"]),
    '"A, B","he said ""yes""","line one\nline two"\r\n',
  );
});
test("CSV neutralises spreadsheet formulas from external content", () => {
  for (const value of ["=SUM(A1:A2)", " +cmd", "-2+1", "@SUM(A1)", "\t=1"])
    assert.ok(csvCell(value).startsWith("\"'"));
  assert.equal(csvCell(null), '""');
});
test("British dates and currency remain clear at daylight-saving boundaries", () => {
  assert.equal(gbTime("2026-07-01T09:00:00Z"), "10:00");
  assert.equal(gbTime("2026-12-01T09:00:00Z"), "09:00");
  assert.equal(gbDate("2026-11-16"), "16 Nov");
  assert.equal(money(9500), "£95");
  assert.equal(money(9575), "£95.75");
});
test("Arrival windows and emergency display use business meanings", () => {
  assert.equal(arrivalWindow("MORNING"), "08:00–12:00");
  assert.equal(arrivalWindow("AFTERNOON"), "12:00–17:00");
  assert.ok(isEmergency("gas_emergency"));
  assert.ok(isEmergency("co_alarm"));
  assert.ok(!isEmergency("complaint"));
  assert.equal(duration(125), "2m 05s");
  assert.equal(duration(null), "Not connected");
});

test("Diary distinguishes UK roleplays stored under the campaign purpose", () => {
  assert.equal(bookingTestLabel("campaign", "ENGINEERING-UK-BW-1107-example"), "UK test");
  assert.equal(bookingTestLabel("campaign", "BW-1107"), null);
  assert.equal(bookingTestLabel("browser_simulation", "EXAMPLE"), "Browser test");
  assert.equal(bookingTestLabel("engineering", "EXAMPLE"), "Engineering test");
});

test("call scopes and follow-up navigation retain the selected customer view", () => {
  assert.equal(callScope("uk_test"), "uk_test");
  assert.equal(callScope("browser_simulation"), "browser_simulation");
  assert.equal(callScope("unknown", "campaign"), "campaign");
  const url = new URL(
    followupHref({
      status: "resolved",
      scope: "uk_test",
      owner: "Sarah",
      q: "Graham",
      notice: "Saved",
    }),
    "https://office.test",
  );
  assert.equal(url.pathname, "/callbacks");
  assert.deepEqual(Object.fromEntries(url.searchParams), {
    status: "resolved",
    scope: "uk_test",
    owner: "Sarah",
    q: "Graham",
    notice: "Saved",
  });
});

test("diary links use the Monday of the visit's real calendar week", () => {
  assert.equal(weekStart("2026-11-18"), "2026-11-16");
  assert.equal(weekStart("2027-01-01"), "2026-12-28");
  assert.equal(weekStart("2026-11-22"), "2026-11-16");
  assert.equal(diaryHref("2026-11-24", "uk_test"), "/bookings?week=2026-11-23&scope=uk_test");
});
