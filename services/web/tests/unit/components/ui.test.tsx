import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "@/components/ui/button";
import { Tag } from "@/components/ui/tag";
import { Slab } from "@/components/ui/slab";
import { Meter } from "@/components/ui/meter";
import { CaseRail } from "@/components/ui/case-rail";
import { FlowRail } from "@/components/ui/rail";
import { Field } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableWrap, Td, Th } from "@/components/ui/data-table";
import { Logo, LogoMark } from "@/components/brand/logo";

describe("Button", () => {
  it("defaults to type=button so it never submits a form by accident", () => {
    render(<Button>Pay</Button>);
    expect(screen.getByRole("button", { name: "Pay" })).toHaveAttribute("type", "button");
  });
  it("can be disabled", () => {
    render(<Button disabled>Pay</Button>);
    expect(screen.getByRole("button", { name: "Pay" })).toBeDisabled();
  });
  it("renders a link when asChild", () => {
    render(
      <Button asChild>
        <a href="/home">Home</a>
      </Button>,
    );
    expect(screen.getByRole("link", { name: "Home" })).not.toHaveAttribute("type");
  });
});

describe("Tag, Slab, Notice, Skeleton", () => {
  it("renders content", () => {
    render(
      <>
        <Tag tone="ret">Refunded</Tag>
        <Slab raised>Panel</Slab>
        <Skeleton className="h-4" />
      </>,
    );
    expect(screen.getByText("Refunded")).toBeInTheDocument();
    expect(screen.getByText("Panel")).toHaveClass("shadow-slab");
  });
  it("announces warnings as alerts and info as status", () => {
    render(
      <>
        <Notice tone="warn" title="Careful">
          Over the cap
        </Notice>
        <Notice>Fine</Notice>
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Over the cap");
    expect(screen.getByRole("status")).toHaveTextContent("Fine");
  });
});

describe("Meter", () => {
  it("draws 20 cells with spent and extra segments", () => {
    const { container } = render(<Meter part={34000} whole={50000} extra={6000} label="Cap use" />);
    expect(screen.getByRole("img", { name: "Cap use" })).toBeInTheDocument();
    const cells = Array.from(container.querySelectorAll("[data-cell]"));
    expect(cells).toHaveLength(20);
    expect(cells.filter((c) => c.getAttribute("data-cell") === "spent")).toHaveLength(14);
    expect(cells.filter((c) => c.getAttribute("data-cell") === "extra")).toHaveLength(2);
  });
  it("shows an empty bar when nothing is spent", () => {
    const { container } = render(<Meter part={0} whole={50000} label="Cap use" />);
    expect(container.querySelectorAll('[data-cell="free"]')).toHaveLength(20);
  });
});

describe("CaseRail", () => {
  it("marks the current step", () => {
    render(<CaseRail state="OFFERED" />);
    expect(screen.getByText("Offer").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Resolved").closest("li")).not.toHaveAttribute("aria-current");
  });
});

describe("Field", () => {
  it("connects label, hint and error to the input", () => {
    render(<Field id="amt" label="Cap" hint="Whole dollars" error="Too high" />);
    const input = screen.getByLabelText("Cap");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")).toBe("amt-hint amt-error");
    expect(screen.getByRole("alert")).toHaveTextContent("Too high");
  });
  it("has no error wiring when valid", () => {
    render(<Field id="amt" label="Cap" />);
    expect(screen.getByLabelText("Cap")).not.toHaveAttribute("aria-invalid");
  });
});

describe("Table", () => {
  it("scrolls inside its wrapper and gives headers column scope", () => {
    render(
      <TableWrap data-testid="wrap">
        <Table>
          <thead>
            <tr>
              <Th>Order</Th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <Td>ORD-1</Td>
            </tr>
          </tbody>
        </Table>
      </TableWrap>,
    );
    expect(screen.getByTestId("wrap")).toHaveClass("overflow-x-auto");
    expect(screen.getByRole("columnheader", { name: "Order" })).toHaveAttribute("scope", "col");
  });
});

describe("Logo", () => {
  it("renders the three-plane cube and the wordmark", () => {
    const { container } = render(<Logo />);
    expect(container.querySelectorAll("polygon")).toHaveLength(3);
    expect(screen.getByText(/SafePay/)).toBeInTheDocument();
    expect(screen.getByText("AI")).toBeInTheDocument();
  });
  it("has a one-tone mark that follows the text colour", () => {
    const { container } = render(<LogoMark tone="mono" />);
    expect(container.querySelector("polygon")).toHaveAttribute("fill", "currentColor");
  });
});

describe("FlowRail and Slab shadow", () => {
  it("marks the buying step the buyer is on", () => {
    render(<FlowRail step={1} />);
    expect(screen.getByText("Cart").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Approve").closest("li")).not.toHaveAttribute("aria-current");
  });
  it("uses the flare shadow for money at risk", () => {
    render(<Slab raised="flare">Money</Slab>);
    expect(screen.getByText("Money")).toHaveClass("shadow-slab-flare");
    expect(screen.getByText("Money")).not.toHaveClass("shadow-slab");
  });
  it("casts a notched panel's shadow from a wrapper so the clip does not cut it", () => {
    render(
      <Slab raised notched>
        Cut
      </Slab>,
    );
    expect(screen.getByText("Cut")).not.toHaveClass("shadow-slab");
    expect(screen.getByText("Cut").parentElement?.className).toContain("drop-shadow");
  });
  it("fills spent cells with Seal and outlines the cart being reviewed", () => {
    const { container } = render(<Meter part={10000} whole={20000} extra={2000} label="Cap" />);
    expect(container.querySelector('[data-cell="spent"]')).toHaveClass("bg-seal");
    expect(container.querySelector('[data-cell="extra"]')).toHaveClass("border-seal");
  });
});
