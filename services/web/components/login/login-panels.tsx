"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { PersonaPicker } from "@/components/login/persona-picker";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { WakingUp } from "@/components/shared/waking-up";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import {
  HANDLE_PATTERN,
  PASSWORD_MAX,
  PASSWORD_MIN,
  type SessionResponse,
} from "@/lib/api/schemas/auth";
import { homeFor, safeNextPath } from "@/lib/auth/roles";
import { useSession } from "@/lib/auth/session";

interface SignupProblems {
  handle?: string;
  password?: string;
  displayName?: string;
}

/** Client-side mirror of the signup rules; the server stays the authority. */
export function validateSignup(input: {
  handle: string;
  password: string;
  displayName: string;
}): SignupProblems {
  const out: SignupProblems = {};
  if (!HANDLE_PATTERN.test(input.handle)) {
    out.handle =
      "Use 3 to 32 characters: lowercase letters, digits, _ or -. Start with a letter or digit.";
  }
  if (input.password.length < PASSWORD_MIN || input.password.length > PASSWORD_MAX) {
    const lengthRule = `Use ${PASSWORD_MIN} to ${PASSWORD_MAX} characters.`;
    out.password = lengthRule;
  }
  if (input.displayName.trim().length > 64) out.displayName = "Keep it to 64 characters.";
  return out;
}

type Kind = "demo" | "staff" | "signup" | "persona";

/** Sign in, create an account, or try the demo. All end in the role's own home. */
export function LoginPanels() {
  const router = useRouter();
  const params = useSearchParams();
  const { session, refresh } = useSession();
  const [pending, setPending] = React.useState<Kind | null>(null);
  const [error, setError] = React.useState<unknown>(null);
  const [failedKind, setFailedKind] = React.useState<Kind | null>(null);
  const [handle, setHandle] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [newHandle, setNewHandle] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [newName, setNewName] = React.useState("");
  const [problems, setProblems] = React.useState<SignupProblems>({});

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

  async function run(kind: Kind, call: () => Promise<SessionResponse>) {
    lastAttempt.current = () => run(kind, call);
    setPending(kind);
    setError(null);
    setFailedKind(null);
    try {
      await finish(await call());
    } catch (e) {
      setError(e);
      setFailedKind(kind);
      setPending(null);
    }
  }

  function submitSignup(e: React.FormEvent) {
    e.preventDefault();
    const found = validateSignup({
      handle: newHandle,
      password: newPassword,
      displayName: newName,
    });
    setProblems(found);
    if (Object.keys(found).length > 0) return;
    const name = newName.trim();
    void run("signup", () =>
      api.auth.signup({
        handle: newHandle,
        password: newPassword,
        ...(name ? { display_name: name } : {}),
      }),
    );
  }

  const apiError = error instanceof ApiError ? error : null;
  const waking = apiError?.code === "UPSTREAM_WAKING";
  const staffError = failedKind === "staff" && apiError?.code === "UNAUTHENTICATED";
  const handleTaken = failedKind === "signup" && apiError?.code === "HANDLE_TAKEN";
  const signupInvalid =
    failedKind === "signup" &&
    (apiError?.code === "VALIDATION_ERROR" || apiError?.code === "validation_error");
  const personaGone = failedKind === "persona" && apiError?.status === 404;
  const inline = staffError || handleTaken || signupInvalid || personaGone;

  return (
    <div className="grid gap-8 lg:grid-cols-3">
      <Slab className="flex flex-col gap-4">
        <Tag className="self-start">Buyer · Merchant · Operator · Reviewer</Tag>
        <h2 className="font-display text-3xl font-extrabold">Sign in.</h2>
        <p className="text-mute">
          Your own account, or a seeded staff account. Each login has exactly one role.
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
            autoCapitalize="none"
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

      <Slab className="flex flex-col gap-4">
        <Tag tone="seal" className="self-start">
          New buyer
        </Tag>
        <h2 className="font-display text-3xl font-extrabold">Create account.</h2>
        <p className="text-mute">A buyer account for the sandbox. No email. Test funds only.</p>
        <form className="flex flex-col gap-4" onSubmit={submitSignup} noValidate>
          <Field
            id="new-handle"
            label="New account name"
            hint="3 to 32 characters: a-z, 0-9, _ or -"
            autoComplete="username"
            autoCapitalize="none"
            value={newHandle}
            onChange={(e) => setNewHandle(e.target.value)}
            error={handleTaken ? "That handle is taken. Pick a different one." : problems.handle}
            required
          />
          <Field
            id="new-passphrase"
            label="Choose a passphrase"
            type="password"
            hint={`${PASSWORD_MIN} to ${PASSWORD_MAX} characters`}
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            error={problems.password}
            required
          />
          <Field
            id="new-display-name"
            label="Display name (optional)"
            autoComplete="nickname"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            error={problems.displayName}
          />
          {signupInvalid && (
            <p role="alert" className="text-xs font-semibold text-flare">
              The server did not accept those details. Check the handle and passphrase rules.
            </p>
          )}
          <Button type="submit" size="lg" disabled={pending !== null}>
            {pending === "signup" ? "Creating…" : "Create account"}
          </Button>
        </form>
      </Slab>

      <Slab raised notched className="flex flex-col gap-4">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-seal">Buyer</p>
        <h2 className="font-display text-3xl font-extrabold">Try the demo.</h2>
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

      <PersonaPicker
        initialHandle={params.get("persona")}
        busy={pending !== null}
        pending={pending === "persona"}
        signInError={failedKind === "persona" ? error : null}
        onSignIn={(h) => void run("persona", () => api.auth.demoPersona(h))}
      />

      <div className="lg:col-span-3" aria-live="polite">
        {waking ? (
          <WakingUp />
        ) : error && !inline ? (
          <ApiErrorNotice error={error} onRetry={() => void lastAttempt.current?.()} />
        ) : null}
      </div>
    </div>
  );
}
