"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { WakingUp } from "@/components/shared/waking-up";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import type { SessionResponse } from "@/lib/api/schemas/auth";
import { homeFor, safeNextPath } from "@/lib/auth/roles";
import { useSession } from "@/lib/auth/session";

/** Demo buyer sign-in and staff sign-in. Both end in the role's own home. */
export function LoginPanels() {
  const router = useRouter();
  const params = useSearchParams();
  const { session, refresh } = useSession();
  const [pending, setPending] = React.useState<"demo" | "staff" | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [handle, setHandle] = React.useState("");
  const [password, setPassword] = React.useState("");

  const next = params.get("next");
  const lastAttempt = React.useRef<(() => Promise<void>) | null>(null);

  React.useEffect(() => {
    if (session.status === "authenticated") {
      router.replace(safeNextPath(next, homeFor(session.role)));
    }
  }, [session, next, router]);

  async function finish(result: SessionResponse) {
    await refresh();
    router.replace(safeNextPath(next, homeFor(result.principal.role)));
  }

  async function run(kind: "demo" | "staff", call: () => Promise<SessionResponse>) {
    lastAttempt.current = () => run(kind, call);
    setPending(kind);
    setError(null);
    try {
      await finish(await call());
    } catch (e) {
      setError(e);
      setPending(null);
    }
  }

  const waking = error instanceof ApiError && error.code === "UPSTREAM_WAKING";
  const staffError = error instanceof ApiError && error.code === "UNAUTHENTICATED";

  return (
    <div className="grid gap-8 lg:grid-cols-2">
      <Slab raised notched className="flex flex-col gap-4">
        <Tag tone="seal" className="self-start">
          Buyer
        </Tag>
        <h2 className="font-display text-3xl font-extrabold">Try it as a buyer.</h2>
        <p className="text-mute">
          One click makes a throwaway buyer account and signs you in. No email. No password. Test
          funds only.
        </p>
        <dl className="border-t border-line text-sm">
          <div className="flex justify-between border-b border-line py-2">
            <dt className="text-dim">Account</dt>
            <dd>demo-buyer-xxxxxxxx</dd>
          </div>
          <div className="flex justify-between border-b border-line py-2">
            <dt className="text-dim">Seats</dt>
            <dd>Capped. When full, you wait.</dd>
          </div>
        </dl>
        <Button
          size="lg"
          disabled={pending !== null}
          onClick={() => void run("demo", () => api.auth.demoSession())}
        >
          {pending === "demo" ? "Starting…" : "Start demo session"}
        </Button>
      </Slab>

      <Slab className="flex flex-col gap-4">
        <Tag className="self-start">Merchant · Operator · Reviewer</Tag>
        <h2 className="font-display text-3xl font-extrabold">Staff sign-in.</h2>
        <p className="text-mute">
          Seeded accounts only. Each login has exactly one role. No signup.
        </p>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void run("staff", () => api.auth.login({ handle, password }));
          }}
        >
          <Field
            id="handle"
            label="Handle"
            autoComplete="username"
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
            required
          />
          <Field
            id="password"
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={staffError ? "Handle or password was not accepted." : undefined}
            required
          />
          <Button type="submit" variant="secondary" size="lg" disabled={pending !== null}>
            {pending === "staff" ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Slab>

      <div className="lg:col-span-2" aria-live="polite">
        {waking ? (
          <WakingUp />
        ) : error && !staffError ? (
          <ApiErrorNotice error={error} onRetry={() => void lastAttempt.current?.()} />
        ) : null}
      </div>
    </div>
  );
}
