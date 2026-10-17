"use client";

import * as React from "react";
import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { formatMoney } from "@/lib/format/money";
import { cn } from "@/lib/utils";

const CAP_CELLS = 20;
const LIT_CELLS = 14;

/** Every figure on this page is an illustration, not account data. */
function Illustration() {
  return <Tag tone="dashed">Illustration</Tag>;
}

function SceneHead({
  n,
  name,
  line1,
  line2,
  body,
}: {
  n: string;
  name: string;
  line1: string;
  line2: string;
  body: string;
}) {
  return (
    <div className="flex flex-col gap-4">
      <span
        aria-hidden="true"
        className="font-display text-8xl font-black leading-none text-transparent [-webkit-text-stroke:2px_var(--seal)] md:text-9xl"
      >
        {n}
      </span>
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-seal">
        {n} · {name}
      </p>
      <h2 className="font-display text-4xl font-black leading-[0.98] md:text-6xl">
        {line1}
        <br />
        <span className="italic text-seal">{line2}</span>
      </h2>
      <p className="max-w-xl text-mute">{body}</p>
    </div>
  );
}

const CARTS = [
  { id: "C-41", shop: "Northwind Audio", amount: 4820, ok: true },
  { id: "C-42", shop: "Lumen Home", amount: 12900, ok: true },
  { id: "C-43", shop: "Standing desk", amount: 62000, ok: false },
] as const;

const CHECKS = [
  "Order inside mandate",
  "Late by 6 days (simulated)",
  "Inside 14-day claim window",
  "Rule LATE-04 applies",
] as const;

/**
 * Landing scroll story. All content is in the markup at rest. When motion is
 * allowed, GSAP only moves things in from a short distance and ticks the
 * cap meter, day counter, checks and refund amount in hard steps.
 */
export function Story() {
  const root = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const el = root.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let cleanup: (() => void) | undefined;
    let cancelled = false;

    void (async () => {
      const { gsap } = await import("gsap");
      const { ScrollTrigger } = await import("gsap/ScrollTrigger");
      if (cancelled) return;
      gsap.registerPlugin(ScrollTrigger);

      const ctx = gsap.context(() => {
        gsap.utils.toArray<HTMLElement>("[data-rise]").forEach((node) => {
          gsap.from(node, {
            y: 28,
            duration: 0.45,
            ease: "steps(4)",
            scrollTrigger: { trigger: node, start: "top 88%", once: true },
          });
        });

        const cells = gsap.utils.toArray<HTMLElement>("[data-cap-cell]");
        const lit = { n: 0 };
        gsap.to(lit, {
          n: LIT_CELLS,
          snap: { n: 1 },
          ease: `steps(${LIT_CELLS})`,
          scrollTrigger: {
            trigger: "[data-scene='mandate']",
            start: "top 60%",
            end: "bottom 70%",
            scrub: true,
          },
          onUpdate: () => cells.forEach((c, i) => c.toggleAttribute("data-lit", i < lit.n)),
        });

        const days = el.querySelector<HTMLElement>("[data-days]");
        const counter = { d: 0 };
        gsap.to(counter, {
          d: 6,
          snap: { d: 1 },
          ease: "steps(6)",
          scrollTrigger: {
            trigger: "[data-scene='protect']",
            start: "top 60%",
            end: "bottom 80%",
            scrub: true,
          },
          onUpdate: () => {
            if (days) days.textContent = `+${counter.d}`;
          },
        });

        const amount = el.querySelector<HTMLElement>("[data-amount]");
        const cents = { v: 0 };
        gsap.to(cents, {
          v: 4820,
          snap: { v: 1 },
          duration: 0.9,
          ease: "steps(12)",
          scrollTrigger: { trigger: "[data-scene='refund']", start: "top 55%", once: true },
          onUpdate: () => {
            if (amount) amount.textContent = `+${formatMoney(cents.v)}`;
          },
        });

        gsap.from("[data-check]", {
          x: -18,
          stagger: 0.14,
          duration: 0.12,
          ease: "steps(1)",
          scrollTrigger: { trigger: "[data-scene='refund']", start: "top 55%", once: true },
        });
      }, el);

      cleanup = () => ctx.revert();
    })();

    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, []);

  return (
    <div ref={root} className="mx-auto max-w-page px-4 pb-24 md:px-10">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b-2 border-line py-6">
        <Link href="/" aria-label="SafePayAI home">
          <Logo />
        </Link>
        <nav
          aria-label="Landing"
          className="flex flex-wrap items-center gap-5 text-xs font-bold uppercase tracking-[0.12em]"
        >
          <a href="#how" className="text-mute hover:text-fg">
            How it works
          </a>
          <Link href="/audit" className="text-mute hover:text-fg">
            Audit log
          </Link>
          <ThemeToggle />
          <Button asChild size="sm">
            <Link href="/login">Sign mandate</Link>
          </Button>
        </nav>
      </header>

      <section className="flex flex-col gap-8 py-20 md:py-28">
        <Tag tone="seal" className="self-start">
          Buyer protection · PayPal sandbox
        </Tag>
        <h1 className="font-display text-6xl font-black leading-[0.9] tracking-tight md:text-8xl">
          Set the cap.
          <br />
          <span className="italic text-seal">The agent shops inside it.</span>
        </h1>
        <p className="max-w-2xl text-lg text-mute">
          You sign a mandate. An AI agent shops inside it. If an order is late or lost, rules decide
          the refund. Not a chatbot. Not a promise.
        </p>
        <div className="flex flex-wrap gap-4">
          <Button asChild size="lg">
            <Link href="/login">Sign your first mandate</Link>
          </Button>
          <Button asChild size="lg" variant="secondary">
            <a href="#how">See it work</a>
          </Button>
        </div>
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">
          Scroll ↓ 01 Mandate · 02 Shop · 03 Protect · 04 Refund
        </p>
      </section>

      <div id="how" className="flex flex-col gap-28 border-t-4 border-fg pt-20">
        <section data-scene="mandate" className="grid items-center gap-10 lg:grid-cols-2">
          <SceneHead
            n="01"
            name="Mandate"
            line1="Sign the"
            line2="limit."
            body="Pick a cap, a scope and an end date. Sign once. That mandate is the only authority the agent has."
          />
          <Slab raised notched data-rise className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <Tag tone="solid-seal">Mandate active</Tag>
              <Illustration />
            </div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">Cap</p>
            <p className="tabular text-5xl font-semibold tracking-tight">{formatMoney(50000)}</p>
            <div
              aria-hidden="true"
              className="grid gap-[3px]"
              style={{ gridTemplateColumns: `repeat(${CAP_CELLS}, minmax(0, 1fr))` }}
            >
              {Array.from({ length: CAP_CELLS }, (_, i) => (
                <div
                  key={i}
                  data-cap-cell
                  {...(i < LIT_CELLS ? { "data-lit": "" } : {})}
                  className="box-border h-5 bg-line data-[lit]:bg-seal"
                />
              ))}
            </div>
            <dl className="border-t border-line text-sm">
              {[
                ["Scope", "Electronics, home"],
                ["Per cart", `${formatMoney(15000)} max`],
                ["Ends", "30 days"],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-line py-2">
                  <dt className="text-dim">{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          </Slab>
        </section>

        <section data-scene="shop" className="grid items-center gap-10 lg:grid-cols-2">
          <SceneHead
            n="02"
            name="Shop"
            line1="The agent proposes."
            line2="The cap decides."
            body="It builds carts. Every cart is checked against your mandate before you see it. Over the line, it's blocked. You approve what's left."
          />
          <div className="flex flex-col gap-3">
            <div className="flex justify-end">
              <Illustration />
            </div>
            {CARTS.map((c) => (
              <Slab
                key={c.id}
                data-rise
                className={cn("flex items-center justify-between gap-4", !c.ok && "border-flare")}
              >
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.12em] text-dim">
                    Cart {c.id}
                  </p>
                  <p className="font-semibold">{c.shop}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="tabular font-semibold">{formatMoney(c.amount)}</span>
                  <Tag tone={c.ok ? "solid-seal" : "flare"}>{c.ok ? "Inside cap" : "Blocked"}</Tag>
                </div>
              </Slab>
            ))}
          </div>
        </section>

        <section data-scene="protect" className="grid items-center gap-10 lg:grid-cols-2">
          <SceneHead
            n="03"
            name="Protect"
            line1="6 days late."
            line2="Case opened. No forms."
            body="Delivery is checked against the promised date. Miss it and a case opens by itself. No forms. No waiting on hold."
          />
          <Slab data-rise className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">
                ORD-1184 · Northwind Audio
              </p>
              <Tag tone="flare">Late · simulated</Tag>
            </div>
            <ol className="grid grid-cols-4 gap-2 text-[11px] font-bold uppercase tracking-[0.08em]">
              {["Ordered", "Shipped", "Due Apr 8", "Case"].map((s, i) => (
                <li
                  key={s}
                  className={cn(
                    "border-t-4 pt-2",
                    i === 3 ? "border-flare text-flare" : "border-fg",
                  )}
                >
                  {s}
                </li>
              ))}
            </ol>
            <p className="font-display text-6xl font-black text-flare">
              <span data-days>+6</span>
            </p>
            <p className="text-sm text-mute">days past the promised date</p>
            <p className="text-xs text-dim">Carrier status is simulated in the sandbox.</p>
          </Slab>
        </section>

        <section data-scene="refund" className="grid items-center gap-10 lg:grid-cols-2">
          <SceneHead
            n="04"
            name="Refund"
            line1="Rules decide."
            line2="Refund sent."
            body="A deterministic policy engine reads the case. Every check is shown. The refund goes out through PayPal, funded by the merchant."
          />
          <Slab raised notched data-rise className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">
                Policy engine · case ORD-1184
              </p>
              <Illustration />
            </div>
            <ul className="border-t border-line text-sm">
              {CHECKS.map((c) => (
                <li
                  key={c}
                  data-check
                  className="flex items-center justify-between border-b border-line py-2"
                >
                  <span>{c}</span>
                  <Tag tone="seal">Pass</Tag>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex items-center justify-between bg-ret px-4 py-3 text-on-ret">
              <span className="font-bold uppercase tracking-[0.08em]">Refund sent</span>
              <span data-amount className="tabular text-3xl font-semibold tracking-tight">
                +{formatMoney(4820)}
              </span>
            </div>
            <p className="text-xs text-dim">Merchant-funded via PayPal.</p>
          </Slab>
        </section>
      </div>

      <section className="mt-28 flex flex-col items-start gap-6 border-t-4 border-fg pt-12">
        <h2 className="font-display text-5xl font-black md:text-7xl">
          Set once.
          <br />
          <span className="italic text-seal">Enforced always.</span>
        </h2>
        <Button asChild size="lg">
          <Link href="/login">Sign your first mandate</Link>
        </Button>
        <p className="text-sm text-dim">
          Sandbox build. Test funds only. Carrier data is simulated.
        </p>
      </section>
    </div>
  );
}
