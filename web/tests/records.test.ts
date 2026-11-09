import test from "node:test";
import assert from "node:assert/strict";
import { csvCell, csvRow } from "../lib/csv.ts";
import { arrivalWindow, duration, gbDate, gbTime, isEmergency, money } from "../lib/format.ts";
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
