import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useState } from "react";

import { TemporaryPassword } from "./temporary-password";
import type { UserWithTemporaryPassword } from "../../src/lib/api/types";

afterEach(cleanup);

describe("TemporaryPassword", () => {
  it("removes the temporary password from rendered state when closed", () => {
    function Wrapper() {
      const [result, setResult] = useState<UserWithTemporaryPassword | null>({
        user: {
          id: "1",
          email: "employee@example.com",
          full_name: "Employee",
          role: "EMPLOYEE",
          is_active: true,
          must_change_password: true,
        },
        temporary_password: "one-time-secret",
      });
      return result ? (
        <TemporaryPassword result={result} onClose={() => setResult(null)} />
      ) : (
        <p>Закрыто</p>
      );
    }
    render(<Wrapper />);
    expect(screen.getByText("one-time-secret")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Понятно" }));
    expect(screen.queryByText("one-time-secret")).toBeNull();
    expect(screen.getByText("Закрыто")).toBeTruthy();
  });
});
