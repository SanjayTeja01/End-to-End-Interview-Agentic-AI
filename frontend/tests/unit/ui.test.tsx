import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge, ErrorBox, Progress, Table } from "@/components/ui";

describe("ui components", () => {
  it("renders badges with readable text", () => {
    render(<Badge>pending_approval</Badge>);
    expect(screen.getByText("pending approval")).toBeInTheDocument();
  });
  it("renders error alerts", () => {
    render(<ErrorBox message="Boom" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Boom");
  });
  it("exposes progress for assistive tech", () => {
    render(<Progress value={0.5} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
  });
  it("shows empty state for tables", () => {
    render(<Table head={["A"]} rows={[]} empty="Nothing" />);
    expect(screen.getByText("Nothing")).toBeInTheDocument();
  });
});
