import * as React from "react";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { recorded } from "../../mocks/handlers";

/** Render with a fresh query client that never retries, so failures show at once. */
export function renderApp(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
  });
  const result = render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
  return { ...result, qc };
}

type Method = "get" | "post" | "put";

/** Replace one route's answer for the current test, still recording the call. */
export function answer(
  method: Method,
  path: string,
  status: number,
  body: unknown,
  headers?: Record<string, string>,
) {
  server.use(
    recorded(method, path, () =>
      body === undefined
        ? new HttpResponse(null, { status, headers })
        : HttpResponse.json(body as Record<string, unknown>, { status, headers }),
    ),
  );
}
