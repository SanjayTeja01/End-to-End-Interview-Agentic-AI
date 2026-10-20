import { describe, expect, it } from "vitest";
import { label, mmss, pct } from "@/lib/format";

describe("format helpers", () => {
  it("formats timers", () => {
    expect(mmss(0)).toBe("00:00");
    expect(mmss(125.9)).toBe("02:05");
    expect(mmss(-5)).toBe("00:00");
  });
  it("labels snake_case", () => expect(label("pending_approval")).toBe("Pending Approval"));
  it("handles empty scores", () => {
    expect(pct(null)).toBe("–");
    expect(pct(72.456, 1)).toBe("72.5");
  });
});
