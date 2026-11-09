/** RFC 4180 quoting with spreadsheet-formula neutralisation for caller content. */
export function csvCell(value: unknown): string {
  let text = value == null ? "" : String(value);
  if (/^\s*[=+\-@\t\r]/u.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}
export function csvRow(values: unknown[]): string {
  return values.map(csvCell).join(",") + "\r\n";
}
