"use client";

import * as React from "react";

import { api } from "@/lib/api";

/**
 * Fire-and-forget nudge so sleeping backend hosts start waking before they are needed.
 * Renders nothing, never blocks, and swallows every failure (api.ops.wake resolves to null).
 */
export function WakePing() {
  React.useEffect(() => {
    void api.ops.wake();
  }, []);
  return null;
}
