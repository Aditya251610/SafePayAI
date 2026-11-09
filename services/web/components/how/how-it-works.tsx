"use client";

import * as React from "react";
import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { CaseRail } from "@/components/ui/case-rail";
import { Meter } from "@/components/ui/meter";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { REFUND_FUNDING_NOTICE, SIMULATED_CARRIER_LABEL } from "@/lib/honesty/copy";
import { formatMoney } from "@/lib/format/money";
import { cn } from "@/lib/utils";

type Actor = "paypal" | "ai" | "rules" | "buyer";

const ACTOR: Record<Actor, { label: string; tone: "seal" | "flare" | "ret" | "neutral" }> = {
  paypal: { label: "PayPal does", tone: "seal" },
  ai: { label: "AI does", tone: "flare" },
  rules: { label: "Rules decide", tone: "ret" },
  buyer: { label: "You do", tone: "neutral" },
};

function Chip({ actor }: { actor: Actor }) {
  const a = ACTOR[actor];
  return <Tag tone={a.tone}>{a.label}</Tag>;
}

function Illustration() {
  return <Tag tone="dashed">Illustration</Tag>;
}

interface StepProps {
  n: string;
  scene: string;
  title: string;
  actors: Actor[];
  body: string;
  facts: string[];
  children: React.ReactNode;
}

function Step({ n, scene, title, actors, body, facts, children }: StepProps) {
  return (
    <li data-scene={scene} className="grid gap-8 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        <span
          aria-hidden="true"
          className="font-display text-7xl font-black leading-none text-transparent [-webkit-text-stroke:2px_var(--seal)] md:text-8xl"
        >
          {n}
        </span>
        <div className="flex flex-wrap gap-2">
          {actors.map((a) => (
            <Chip key={a} actor={a} />
          ))}
        </div>
        <h3 className="font-display text-3xl font-black leading-[1] md:text-5xl">{title}</h3>
        <p className="max-w-xl text-mute">{body}</p>
        <ul className="max-w-xl border-t border-line text-sm">
          {facts.map((f) => (
            <li key={f} className="border-b border-line py-2">
              {f}
            </li>
          ))}
        </ul>
      </div>
      <div data-rise className="flex min-w-0 flex-col gap-3">
        {children}
      </div>
    </li>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line py-2">
      <dt className="text-dim">{k}</dt>
      <dd className="text-right">{v}</dd>
    </div>
  );
}

const LEGEND: { actor: Actor; lines: string[] }[] = [
  {
    actor: "paypal",
    lines: [
      "Hosts the sandbox approval page you are sent to",
      "Creates and captures the order (Orders v2)",
      "Sends the refund when the rules approve one",
    ],
  },
  {
    actor: "ai",
    lines: [
      "Turns your words into a draft cart",
      "Reads a problem report and suggests a label",
      "Holds no PayPal credentials and cannot pay",
    ],
  },
  {
    actor: "rules",
    lines: [
      "Check every cart against your signed mandate",
      "Detect late or lost orders from the carrier clock",
      "Set the refund amount and tier. Nothing else does",
    ],
  },
];

const DRAFT_CHECKS: [string, string][] = [
  ["Draft: wired headphones", "Draft"],
  ["Inside the cap", "Pass"],
  ["Shop is in scope", "Pass"],
  ["Under the per-cart limit", "Pass"],
];

const PAYPAL_STEPS: [string, Actor][] = [
  ["Checkout creates the order", "paypal"],
  ["You approve it on PayPal (sandbox)", "buyer"],
  ["Checkout captures it", "paypal"],
];

/**
 * The end-to-end story: where PayPal is used, what the AI does, what the
 * rules decide. All content is in the markup at rest; GSAP only moves it in
 * from a short distance when motion is allowed.
 */
export function HowItWorks() {
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

        gsap.from("[data-chain-block]", {
          x: -16,
          stagger: 0.18,
          duration: 0.12,
          ease: "steps(1)",
          scrollTrigger: { trigger: "[data-scene='audit']", start: "top 60%", once: true },
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
          aria-label="How it works"
          className="flex flex-wrap items-center gap-5 text-xs font-bold uppercase tracking-[0.12em]"
        >
          <Link href="/" className="text-mute hover:text-fg">
            Home
          </Link>
          <Link href="/audit" className="text-mute hover:text-fg">
            Audit log
          </Link>
          <ThemeToggle />
          <Button asChild size="sm">
            <Link href="/login">Sign in</Link>
          </Button>
        </nav>
      </header>

      <section className="flex flex-col gap-6 py-16 md:py-24">
        <Tag tone="seal" className="self-start">
          PayPal sandbox · test funds
        </Tag>
        <h1 className="font-display text-5xl font-black leading-[0.92] tracking-tight md:text-8xl">
          Where PayPal fits.
          <br />
          <span className="italic text-seal">What the AI does.</span>
        </h1>
        <p className="max-w-2xl text-lg text-mute">
          One purchase, start to finish. Each step says who acts: PayPal, the AI, or the rules. The
          figures below are an illustration, not account data.
        </p>
      </section>

      <section aria-labelledby="legend-h" className="flex flex-col gap-4">
        <h2 id="legend-h" className="border-t-4 border-fg pt-3 text-xl font-semibold">
          Who does what
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          {LEGEND.map((l) => (
            <Slab key={l.actor} className="flex flex-col gap-3">
              <Chip actor={l.actor} />
              <ul className="flex flex-col gap-2 text-sm text-mute">
                {l.lines.map((line) => (
                  <li key={line} className="border-t border-line pt-2">
                    {line}
                  </li>
                ))}
              </ul>
            </Slab>
          ))}
        </div>
      </section>

      <section aria-labelledby="ai-h" className="my-16">
        <Slab raised="flare" className="flex flex-col gap-3">
          <Tag tone="flare" className="self-start">
            The AI boundary
          </Tag>
          <h2 id="ai-h" className="font-display text-3xl font-black leading-[1.05] md:text-5xl">
            AI classifies and drafts. It never decides money.
          </h2>
          <p className="max-w-3xl text-lg text-mute">
            On any error or low confidence it hands the case to a person.
          </p>
        </Slab>
      </section>

      <ol aria-label="The journey, seven steps" className="flex flex-col gap-24">
        <Step
          n="01"
          scene="mandate"
          title="You sign a mandate."
          actors={["buyer"]}
          body="A spending cap, which shops, an end date and the refund terms. Sign once. That mandate is the only authority anything else gets."
          facts={[
            "The cap, the per-cart limit and the end date are fixed when you sign.",
            "You can revoke it. That stops future purchases.",
          ]}
        >
          <Slab raised notched className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <Tag tone="solid-seal">Mandate active</Tag>
              <Illustration />
            </div>
            <p className="tabular text-4xl font-semibold tracking-tight">{formatMoney(50000)}</p>
            <Meter part={14} whole={20} label="14 of 20 cap cells used. Illustration." />
            <dl className="border-t border-line text-sm">
              <Row k="Shops" v="Electronics, home" />
              <Row k="Per cart" v={`${formatMoney(15000)} max`} />
              <Row k="Ends" v="30 days" />
              <Row k="Refund terms" v="Late or lost, 14-day window" />
            </dl>
          </Slab>
        </Step>

        <Step
          n="02"
          scene="agent"
          title="The agent drafts. Rules check."
          actors={["ai", "rules"]}
          body="You describe what you want in words. The AI shopping agent drafts a cart from the seeded catalog. Then plain rules check that draft against your mandate."
          facts={[
            "The agent never holds PayPal credentials and never pays.",
            "Prices come from the catalog, not from the agent's words.",
            "If the agent fails or is unsure, you get the form instead.",
          ]}
        >
          <Slab className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Tag tone="flare">AI drafted · rules decide</Tag>
              <Illustration />
            </div>
            <p className="border-l-4 border-line-strong pl-3 text-sm italic text-mute">
              &ldquo;Headphones under $150&rdquo;
            </p>
            <ul className="border-t border-line text-sm">
              {DRAFT_CHECKS.map(([k, v], i) => (
                <li key={k} className="flex items-center justify-between border-b border-line py-2">
                  <span>{k}</span>
                  <Tag tone={i === 0 ? "flare" : "ret"}>{v}</Tag>
                </li>
              ))}
            </ul>
            <p className="text-xs text-dim">The agent can propose. It cannot approve or pay.</p>
          </Slab>
        </Step>

        <Step
          n="03"
          scene="paypal"
          title="PayPal sandbox takes the payment."
          actors={["paypal", "buyer"]}
          body="You are sent to PayPal's sandbox to approve the order. When you come back, checkout captures it through PayPal Orders v2. Test funds only."
          facts={[
            "Only the PayPal adapter holds PayPal credentials.",
            "The order and capture ids appear on your receipt.",
          ]}
        >
          <Slab raised notched className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Tag tone="seal">PayPal sandbox order</Tag>
              <Illustration />
            </div>
            <ol className="flex flex-col text-sm">
              {PAYPAL_STEPS.map(([k, who], i) => (
                <li key={k} className="flex items-center gap-3 border-b border-line py-2">
                  <span className="tabular w-6 font-mono text-dim">{i + 1}</span>
                  <span className="flex-1">{k}</span>
                  <Chip actor={who} />
                </li>
              ))}
            </ol>
          </Slab>
        </Step>

        <Step
          n="04"
          scene="carrier"
          title="Tracking is a clock we control."
          actors={["rules"]}
          body="Delivery status comes from a simulated carrier that we run. It is not real carrier data and not PayPal data. It exists so late and lost orders can be shown on demand."
          facts={["Every carrier screen is labelled, so nobody mistakes it for the real thing."]}
        >
          <Slab className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Tag tone="dashed">{SIMULATED_CARRIER_LABEL}</Tag>
              <Illustration />
            </div>
            <ol className="grid grid-cols-4 gap-2 text-[11px] font-bold uppercase tracking-[0.08em]">
              {["Ordered", "Shipped", "Due", "Late"].map((s, i) => (
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
            <p className="text-sm text-mute">
              Six days past the promised date, on the sandbox clock.
            </p>
          </Slab>
        </Step>

        <Step
          n="05"
          scene="rules"
          title="Rules spot it and make an offer."
          actors={["rules"]}
          body="A deterministic policy engine reads the order, the carrier record and your mandate terms. If a late or lost order qualifies, you see an offer. Every check is listed."
          facts={[
            "The same inputs always give the same answer.",
            "Where the AI helps, it only reads your report and suggests a label.",
            "Unclear or unusual cases go to a person.",
          ]}
        >
          <Slab raised notched className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Tag tone="ret">Rules decided</Tag>
              <Illustration />
            </div>
            <CaseRail state="OFFERED" />
            <ul className="border-t border-line text-sm">
              {[
                "Order inside mandate",
                "Late by 6 days (simulated)",
                "Inside the claim window",
              ].map((c) => (
                <li key={c} className="flex items-center justify-between border-b border-line py-2">
                  <span>{c}</span>
                  <Tag tone="seal">Pass</Tag>
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between bg-ret px-4 py-3 text-on-ret">
              <span className="font-bold uppercase tracking-[0.08em]">Offer</span>
              <span className="tabular text-2xl font-semibold">{formatMoney(4820)}</span>
            </div>
          </Slab>
        </Step>

        <Step
          n="06"
          scene="refund"
          title="PayPal sends the refund."
          actors={["paypal", "rules"]}
          body="When you accept, the refund goes out through PayPal's refund API. The merchant funds it. The amount is the one the rules set."
          facts={[
            `${REFUND_FUNDING_NOTICE}.`,
            "Large or unusual refunds need your explicit approval first.",
          ]}
        >
          <Slab className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Tag className="h-auto whitespace-normal py-1" tone="seal">
                Rules decided · refund via PayPal (merchant-funded)
              </Tag>
              <Illustration />
            </div>
            <div className="flex items-center justify-between bg-ret px-4 py-3 text-on-ret">
              <span className="font-bold uppercase tracking-[0.08em]">Refund sent</span>
              <span className="tabular text-2xl font-semibold">+{formatMoney(4820)}</span>
            </div>
            <p className="text-xs text-dim">Sandbox refund, test funds.</p>
          </Slab>
        </Step>

        <Step
          n="07"
          scene="audit"
          title="Every money action is logged."
          actors={["rules"]}
          body="Mandate signed, order captured, case opened, offer made, refund sent: each lands in an append-only audit log. Each entry carries the hash of the one before it, and a check re-reads the chain."
          facts={["Anyone signed in can open the audit log and run the chain check."]}
        >
          <Slab className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">Audit chain</p>
              <Illustration />
            </div>
            <ol className="flex flex-col gap-2">
              {["mandate.signed", "order.captured", "case.opened", "refund.sent"].map((e, i) => (
                <li
                  key={e}
                  data-chain-block
                  className="flex items-center justify-between gap-2 border-2 border-line-strong px-3 py-2 text-sm"
                >
                  <span className="font-mono">{e}</span>
                  <span className="font-mono text-xs text-dim">#{i + 1} · prev hash</span>
                </li>
              ))}
            </ol>
          </Slab>
        </Step>
      </ol>

      <section className="mt-28 flex flex-col items-start gap-6 border-t-4 border-fg pt-12">
        <h2 className="font-display text-4xl font-black md:text-6xl">See it on real screens.</h2>
        <div className="flex flex-wrap gap-4">
          <Button asChild size="lg">
            <Link href="/login">Try the demo</Link>
          </Button>
          <Button asChild size="lg" variant="secondary">
            <Link href="/">Back to home</Link>
          </Button>
        </div>
        <p className="text-sm text-dim">
          Sandbox build. Test funds only. Carrier data is simulated. Not affiliated with PayPal.
        </p>
      </section>
    </div>
  );
}
