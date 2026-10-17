"use client";

import * as React from "react";
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { api, onUnauthenticated } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import type { Me } from "@/lib/api/schemas/auth";
import type { Role } from "@/lib/api/schemas/common";

export const SESSION_KEY = ["session"] as const;

export type SessionState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error"; error: ApiError | Error; waking: boolean }
  | { status: "authenticated"; me: Me; role: Role };

interface SessionContextValue {
  session: SessionState;
  /** Re-read /auth/me, e.g. after sign-in. */
  refresh: () => Promise<void>;
  /** Sign out and drop every cached read. */
  signOut: () => Promise<void>;
}

const SessionContext = React.createContext<SessionContextValue | null>(null);

/** Drop every cached read except the session itself. */
function clearUserData(qc: QueryClient): void {
  qc.removeQueries({ predicate: (q) => q.queryKey[0] !== SESSION_KEY[0] });
}

/** Loads /auth/me once and keeps it fresh. A 401 anywhere returns to anonymous. */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const [signedOut, setSignedOut] = React.useState(false);
  const query = useQuery({
    queryKey: SESSION_KEY,
    queryFn: ({ signal }) => api.auth.me(signal),
    staleTime: 60_000,
  });

  React.useEffect(
    () =>
      onUnauthenticated(() => {
        clearUserData(qc);
        setSignedOut(true);
      }),
    [qc],
  );

  const session = React.useMemo<SessionState>(() => {
    if (signedOut) return { status: "anonymous" };
    if (query.data) return { status: "authenticated", me: query.data, role: query.data.role };
    if (query.isError) {
      const err = query.error;
      if (err instanceof ApiError && err.code === "UNAUTHENTICATED") return { status: "anonymous" };
      return {
        status: "error",
        error: err,
        waking: err instanceof ApiError && err.code === "UPSTREAM_WAKING",
      };
    }
    return { status: "loading" };
  }, [signedOut, query.data, query.isError, query.error]);

  const value = React.useMemo<SessionContextValue>(
    () => ({
      session,
      refresh: async () => {
        setSignedOut(false);
        await qc.invalidateQueries({ queryKey: SESSION_KEY });
      },
      signOut: async () => {
        try {
          await api.auth.logout();
        } finally {
          clearUserData(qc);
          setSignedOut(true);
        }
      },
    }),
    [session, qc],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = React.useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}
