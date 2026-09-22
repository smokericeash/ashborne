import { describe, expect, it } from "vitest";
import { initials, parseApiTimestamp } from "./utils";

describe("API time and identity formatting", () => {
  it("treats timezone-less API datetimes as UTC", () => {
    expect(parseApiTimestamp("2026-09-20T18:00:00").getTime()).toBe(
      Date.parse("2026-09-20T18:00:00Z"),
    );
    expect(parseApiTimestamp("2026-09-20T11:00:00-07:00").getTime()).toBe(
      Date.parse("2026-09-20T18:00:00Z"),
    );
  });

  it("uses the ASHBORNE initial as the empty-name fallback", () => {
    expect(initials()).toBe("A");
  });
});
