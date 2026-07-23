import { describe, expect, it } from "vitest";

import { formatStatus } from "./status";

describe("formatStatus", () => {
  it("returns a user-safe label for unavailable dependencies", () => {
    expect(formatStatus("unavailable")).toBe("Недоступен");
  });
});
