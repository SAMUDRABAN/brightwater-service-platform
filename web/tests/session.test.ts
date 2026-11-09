import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { canonicalOfficeOrigin, sessionFormat, safeReturnPath, sameOrigin } =
  require("../lib/session.ts") as typeof import("../lib/session");
test("only opaque staff-session syntax passes the proxy gate; API validates actual sessions", () => {
  assert.equal(sessionFormat("bwstaff_" + "a".repeat(43)), true);
  for (const token of [
    undefined,
    "",
    "office",
    "Basic abc",
    "legacy.payload",
    "bwstaff_short",
    "bwstaff_" + "a".repeat(44),
  ])
    assert.equal(sessionFormat(token), false);
});
test("return targets are office paths, never external redirects", () => {
  assert.equal(safeReturnPath("/customers"), "/customers");
  assert.equal(
    safeReturnPath("/calls/12345678-1234-1234-1234-123456789012"),
    "/calls/12345678-1234-1234-1234-123456789012",
  );
  for (const value of [
    "//evil.test",
    "https://evil.test",
    "/login",
    "/api/calls/a/recording",
    "/customers?next=https://evil.test",
    "/%2f%2fevil.test",
    null,
  ]) {
    assert.equal(safeReturnPath(value), "/morning");
  }
});
test("form origins must match HTTPS host; HTTP is explicit local loopback only", () => {
  assert.equal(sameOrigin("https://office.example.test", "office.example.test"), true);
  assert.equal(sameOrigin("https://evil.test", "office.example.test"), false);
  assert.equal(sameOrigin(null, "office.example.test"), false);
  assert.equal(sameOrigin("http://office.example.test", "office.example.test", true), false);
  assert.equal(sameOrigin("http://localhost:3000", "localhost:3000", true), true);
  assert.equal(sameOrigin("http://localhost:3000", "localhost:3000"), false);
});
test("canonical redirects use configured public HTTPS origin, never internal upstream", () => {
  const upstream = new URL("http://0.0.0.0:3000/customers");
  const publicOrigin = canonicalOfficeOrigin("office.example.test");
  assert.equal(publicOrigin, "https://office.example.test");
  const destination = new URL("/login", publicOrigin!);
  destination.searchParams.set("next", safeReturnPath(upstream.pathname));
  assert.equal(destination.toString(), "https://office.example.test/login?next=%2Fcustomers");
  for (const value of [
    undefined,
    "",
    "localhost",
    "office.localhost",
    "https://office.example.test",
    "office.example.test:3000",
    "office.example.test/evil",
    "evil@office.example.test",
    "office.example.test,evil.test",
    "office..test",
    " office.test",
    "office.test\n",
    "-office.test",
  ]) {
    assert.equal(canonicalOfficeOrigin(value), null);
  }
});
