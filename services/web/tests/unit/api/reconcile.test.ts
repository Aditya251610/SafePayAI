import { describe, expect, it } from "vitest";
import { pollUntil } from "@/lib/api";

describe("pollUntil", () => {
  it("returns immediately when the first read is settled", async () => {
    const r = await pollUntil(
      async () => "CAPTURED",
      (v) => v === "CAPTURED",
    );
    expect(r).toEqual({ value: "CAPTURED", settled: true });
  });

  it("polls until settled", async () => {
    const seq = ["CAPTURE_PENDING", "CAPTURE_PENDING", "CAPTURED"];
    let i = 0;
    const sleeps: number[] = [];
    const r = await pollUntil(
      async () => seq[Math.min(i++, seq.length - 1)] as string,
      (v) => v === "CAPTURED",
      { intervalMs: 3000, sleep: async (ms) => void sleeps.push(ms) },
    );
    expect(r.settled).toBe(true);
    expect(sleeps).toEqual([3000, 3000]);
  });

  it("stops at the timeout with the last value and settled=false", async () => {
    let t = 0;
    const r = await pollUntil(
      async () => "PENDING",
      () => false,
      {
        intervalMs: 3000,
        timeoutMs: 9000,
        now: () => t,
        sleep: async (ms) => void (t += ms),
      },
    );
    expect(r).toEqual({ value: "PENDING", settled: false });
    expect(t).toBe(9000);
  });

  it("stops when aborted", async () => {
    const ctl = new AbortController();
    ctl.abort();
    const r = await pollUntil(
      async () => "X",
      () => false,
      { signal: ctl.signal },
    );
    expect(r.settled).toBe(false);
  });
});
