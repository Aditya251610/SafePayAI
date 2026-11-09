"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import { groupPersonas, personaBlurb, personaName } from "@/lib/auth/personas";

interface Props {
  /** Handle to preselect, from a deep link such as /login?persona=buyer-alex. */
  initialHandle?: string | null;
  busy: boolean;
  pending: boolean;
  onSignIn: (handle: string) => void;
  /** An error from the last picker sign-in. A 404 is shown here; the rest use the shared notice. */
  signInError?: unknown;
}

/** Fourth path on /login: sign in as a seeded account. No password is ever typed or stored. */
export function PersonaPicker({ initialHandle, busy, pending, onSignIn, signInError }: Props) {
  const list = useQuery({
    queryKey: ["demo-personas"] as const,
    queryFn: ({ signal }) => api.auth.demoPersonas(signal),
    retry: false,
    staleTime: 60_000,
  });
  const [chosen, setChosen] = React.useState<string | null>(initialHandle ?? null);

  const personas = list.data?.personas;
  const groups = React.useMemo(() => groupPersonas(personas ?? []), [personas]);
  const selected =
    personas?.find((p) => p.handle === chosen) ?? personas?.find((p) => p.role === "buyer");
  const off = list.error instanceof ApiError && list.error.status === 404;
  const gone = signInError instanceof ApiError && signInError.status === 404;

  return (
    <Slab className="flex flex-col gap-4 lg:col-span-3" aria-labelledby="persona-h" role="group">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tag tone="flare">Seeded accounts</Tag>
        <Tag tone="dashed">No password</Tag>
      </div>
      <h2 id="persona-h" className="font-display text-3xl font-extrabold">
        Explore a seeded account.
      </h2>
      <p className="max-w-3xl text-mute">
        Pick a prepared buyer, merchant, operator or reviewer and look around as that role. Each
        account has exactly one role. Test funds only.
      </p>

      {list.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : off ? (
        <Notice tone="info" title="Seeded accounts are off">
          Seeded accounts are off on this deployment. Sign in, create an account or start the demo
          instead.
        </Notice>
      ) : list.isError ? (
        <ApiErrorNotice error={list.error} onRetry={() => void list.refetch()} />
      ) : groups.length === 0 || !selected ? (
        <Notice tone="info" title="No seeded accounts">
          This deployment has no seeded accounts to pick from.
        </Notice>
      ) : (
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            onSignIn(selected.handle);
          }}
        >
          <div className="flex max-w-xl flex-col gap-1.5">
            <label
              htmlFor="persona-select"
              className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
            >
              Account
            </label>
            <select
              id="persona-select"
              value={selected.handle}
              onChange={(e) => setChosen(e.target.value)}
              aria-describedby="persona-blurb"
              className="h-12 border-2 border-line-strong bg-panel px-3 text-base text-fg"
            >
              {groups.map((g) => (
                <optgroup key={g.role} label={g.label}>
                  {g.items.map((p) => (
                    <option key={p.handle} value={p.handle}>
                      {personaName(p)} ({p.handle})
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <p id="persona-blurb" className="max-w-xl border-l-4 border-line-strong pl-3 text-sm">
            <span className="block text-[11px] font-bold uppercase tracking-[0.14em] text-dim">
              What you will see
            </span>
            {personaBlurb(selected)}
          </p>
          {gone && (
            <p role="alert" className="text-xs font-semibold text-flare">
              That seeded account is not available here. Pick another, or sign in normally.
            </p>
          )}
          <Button type="submit" size="lg" className="self-start" disabled={busy}>
            {pending ? "Signing in…" : `Sign in as ${personaName(selected)}`}
          </Button>
        </form>
      )}
    </Slab>
  );
}
