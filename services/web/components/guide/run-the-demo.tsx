"use client";

import * as React from "react";
import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import { Button } from "@/components/ui/button";
import { CaseRail } from "@/components/ui/case-rail";
import { Meter } from "@/components/ui/meter";
import { Notice } from "@/components/ui/notice";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import {
  ACTOR_LABEL,
  LIMITS,
  PERSONA_TABLE,
  STEPS,
  personaHref,
  type Actor,
  type GuideStep,
} from "@/lib/guide/content";
import { SIMULATED_CARRIER_LABEL } from "@/lib/honesty/copy";

const ACTOR_TONE: Record<Actor, "seal" | "flare" | "ret" | "neutral"> = {
  paypal: "seal",
  ai: "flare",
  rules: "ret",
  person: "neutral",
};

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="border-t-4 border-fg pt-3 font-display text-3xl font-black md:text-4xl">
      {children}
    </h2>
  );
}

function StepCard({ step }: { step: GuideStep }) {
  const href = personaHref(step);
  return (
    <li data-rise className="grid gap-6 lg:grid-cols-[5rem_1fr]">
      <span
        aria-hidden="true"
        className="font-display text-6xl font-black leading-none text-transparent [-webkit-text-stroke:2px_var(--seal)] md:text-7xl"
      >
        {step.n}
      </span>
      <Slab raised={step.n === "06" ? "flare" : false} className="flex min-w-0 flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Tag tone="solid">{step.who}</Tag>
          {step.persona && <Tag tone="dashed">{step.persona}</Tag>}
        </div>
        <h3 className="font-display text-2xl font-black leading-tight md:text-3xl">{step.title}</h3>
        <Meter
          part={Number(step.n)}
          whole={STEPS.length}
          label={`Step ${step.n} of ${STEPS.length}`}
        />
        <dl className="grid gap-x-6 gap-y-3 text-sm md:grid-cols-[8rem_1fr]">
          <dt className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim">Sign in as</dt>
          <dd className="flex flex-wrap items-center gap-3">
            {href ? (
              <Button asChild size="sm">
                <Link href={href}>Sign in as {step.persona}</Link>
              </Button>
            ) : (
              <span className="text-mute">Stay signed in from the step before.</span>
            )}
          </dd>
          <dt className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim">Open</dt>
          <dd>
            <Link
              href={step.route}
              className="font-mono text-seal underline-offset-4 hover:underline"
            >
              {step.routeLabel ?? step.route}
            </Link>
          </dd>
          <dt className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim">Do</dt>
          <dd>
            <ol className="flex list-decimal flex-col gap-2 pl-5 text-mute">
              {step.click.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ol>
          </dd>
          <dt className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim">You see</dt>
          <dd className="text-mute">{step.see}</dd>
        </dl>
        {step.n === "06" && <CaseRail state="OFFERED" />}
        <p className="flex flex-wrap items-center gap-2 border-t border-line pt-3 text-sm">
          <Tag tone={ACTOR_TONE[step.notice.actor]}>Notice · {ACTOR_LABEL[step.notice.actor]}</Tag>
          <span>{step.notice.text}</span>
        </p>
      </Slab>
    </li>
  );
}

function Code({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto border-2 border-line-strong bg-panel p-4 font-mono text-sm">
      <code>{children}</code>
    </pre>
  );
}

const DOCKER_CMDS = `cp .env.example .env
# edit .env: add your PayPal sandbox client id and secret
docker compose up`;

const DEV_CMDS = `cd services/web
pnpm install
pnpm dev`;

/**
 * "Run the demo": a ten minute path through every role. The content is data in lib/guide, so the
 * markdown guide and this page stay in the same order. GSAP loads lazily and only when motion is
 * allowed; everything is in the markup at rest.
 */
export function RunTheDemo() {
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
            y: 24,
            duration: 0.4,
            ease: "steps(4)",
            scrollTrigger: { trigger: node, start: "top 90%", once: true },
          });
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
          aria-label="Run the demo"
          className="flex flex-wrap items-center gap-5 text-xs font-bold uppercase tracking-[0.12em]"
        >
          <Link href="/" className="text-mute hover:text-fg">
            Home
          </Link>
          <Link href="/how-it-works" className="text-mute hover:text-fg">
            PayPal and AI
          </Link>
          <ThemeToggle />
          <Button asChild size="sm">
            <Link href="/login">Sign in</Link>
          </Button>
        </nav>
      </header>

      <section className="flex flex-col gap-6 py-14 md:py-20">
        <Tag tone="seal" className="self-start">
          About 10 minutes · PayPal sandbox · test funds
        </Tag>
        <h1 className="font-display text-5xl font-black leading-[0.92] tracking-tight md:text-8xl">
          Run the demo.
          <br />
          <span className="italic text-seal">Every role, start to finish.</span>
        </h1>
        <p className="max-w-2xl text-lg text-mute">
          A guided path through the buyer, merchant, operator and reviewer screens. Each step says
          who to sign in as, where to go, and who acts: PayPal, the AI, the rules or a person.
        </p>
      </section>

      <div className="flex flex-col gap-20">
        <section aria-labelledby="what-h" className="flex flex-col gap-4">
          <H2 id="what-h">What you are looking at</H2>
          <p className="max-w-3xl text-lg text-mute">
            A buyer signs a spending mandate that sets what may be bought, and an AI agent drafts
            carts inside it but never pays. When an order is late or lost, plain rules decide the
            refund, and a person handles anything unusual. PayPal&apos;s sandbox takes the payment
            and sends the refund.
          </p>
        </section>

        <section aria-labelledby="before-h" className="flex flex-col gap-4">
          <H2 id="before-h">Before you start</H2>
          <div className="grid gap-4 md:grid-cols-3">
            <Slab className="flex flex-col gap-2">
              <Tag tone="dashed" className="self-start">
                Sandbox only
              </Tag>
              <p className="text-sm text-mute">
                No real money moves. Every payment and refund is a PayPal sandbox test.
              </p>
            </Slab>
            <Slab className="flex flex-col gap-2">
              <Tag tone="flare" className="self-start">
                Slow first request
              </Tag>
              <p className="text-sm text-mute">
                The backend sleeps when idle. The first request can take 30 to 45 seconds. The app
                shows a waking-up notice. Do not stop; it will continue on its own.
              </p>
            </Slab>
            <Slab raised className="flex flex-col gap-2">
              <Tag tone="seal" className="self-start">
                To pay: a sandbox buyer
              </Tag>
              <p className="text-sm text-mute">
                You need a PayPal sandbox <strong>personal (buyer)</strong> account. In
                developer.paypal.com go to Apps &amp; Credentials, Sandbox, Testing Tools, Sandbox
                Accounts, Personal. A business account cannot be the buyer. Use those sandbox
                details only on PayPal&apos;s own page. They never go on this site.
              </p>
            </Slab>
          </div>
        </section>

        <section aria-labelledby="walk-h" className="flex flex-col gap-8">
          <H2 id="walk-h">The walkthrough</H2>
          <Notice tone="info" title="Switching roles">
            Each account has one role. To change role, sign out from the top bar, then use the
            sign-in button in the next step. Seeded accounts need the deployment to have them
            switched on; if the picker says they are off, use Create account or Try the demo for the
            buyer steps.
          </Notice>
          <ol aria-label="Demo steps" className="flex flex-col gap-10">
            {STEPS.map((s) => (
              <StepCard key={s.n} step={s} />
            ))}
          </ol>
        </section>

        <section aria-labelledby="who-h" className="flex flex-col gap-4">
          <H2 id="who-h">Who is who</H2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] border-collapse text-left text-sm">
              <caption className="sr-only">
                Seeded accounts, their role and what they can do
              </caption>
              <thead>
                <tr className="border-b-2 border-line-strong text-[11px] uppercase tracking-[0.14em] text-dim">
                  <th scope="col" className="py-2 pr-4">
                    Account
                  </th>
                  <th scope="col" className="py-2 pr-4">
                    Role
                  </th>
                  <th scope="col" className="py-2">
                    What it can do
                  </th>
                </tr>
              </thead>
              <tbody>
                {PERSONA_TABLE.map((p) => (
                  <tr key={p.handle} className="border-b border-line align-top">
                    <th scope="row" className="py-2 pr-4 font-mono font-normal">
                      {p.handle}
                    </th>
                    <td className="py-2 pr-4">{p.role}</td>
                    <td className="py-2 text-mute">{p.can}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section aria-labelledby="run-h" className="flex flex-col gap-4">
          <H2 id="run-h">Run it yourself</H2>
          <div className="grid gap-4 lg:grid-cols-2">
            <Slab className="flex min-w-0 flex-col gap-3">
              <Tag tone="seal" className="self-start">
                Whole stack with Docker
              </Tag>
              <Code>{DOCKER_CMDS}</Code>
              <ul className="flex list-disc flex-col gap-2 pl-5 text-sm text-mute">
                <li>
                  Put your PayPal sandbox client id and secret in <code>.env</code>. Never commit
                  that file.
                </li>
                <li>
                  Optional: add a Gemini or Groq key to let the AI draft carts. Without one the app
                  falls back to the plain form.
                </li>
                <li>
                  Create the seeded accounts with <code>services/api-gateway/scripts/seed.py</code>.
                  It reads the <code>SEED_*</code> password variables you set yourself.
                </li>
                <li>
                  To show the seeded-account picker set{" "}
                  <code>PS_APIGATEWAY_DEMO_PERSONA_LOGIN=true</code> on the gateway.
                </li>
                <li>
                  Open <code>http://localhost:3000</code>.
                </li>
              </ul>
            </Slab>
            <Slab className="flex min-w-0 flex-col gap-3">
              <Tag tone="neutral" className="self-start">
                Web app only
              </Tag>
              <Code>{DEV_CMDS}</Code>
              <p className="text-sm text-mute">
                Copy <code>.env.example</code> to <code>.env.local</code> and point{" "}
                <code>PS_WEB_GATEWAY_INTERNAL_URL</code> at a running gateway. The app is at{" "}
                <code>http://localhost:3000</code>.
              </p>
            </Slab>
          </div>
        </section>

        <section aria-labelledby="limits-h" className="flex flex-col gap-4">
          <H2 id="limits-h">Honest limits</H2>
          <Slab raised="flare" className="flex flex-col gap-3">
            <Tag tone="dashed" className="self-start">
              {SIMULATED_CARRIER_LABEL} · sandbox
            </Tag>
            <ul className="flex flex-col text-sm">
              {LIMITS.map((l) => (
                <li key={l} className="border-b border-line py-2">
                  {l}
                </li>
              ))}
            </ul>
          </Slab>
        </section>
      </div>

      <section className="mt-24 flex flex-col items-start gap-6 border-t-4 border-fg pt-12">
        <h2 className="font-display text-4xl font-black md:text-6xl">Ready?</h2>
        <div className="flex flex-wrap gap-4">
          <Button asChild size="lg">
            <Link href="/login">Go to sign in</Link>
          </Button>
          <Button asChild size="lg" variant="secondary">
            <Link href="/how-it-works">Where PayPal and AI fit</Link>
          </Button>
        </div>
      </section>
    </div>
  );
}
