/**
 * After a 504 or dropped connection on a money route the action may still
 * have completed. Read the real state until it settles instead of retrying
 * the POST (contract section 6).
 */
export interface PollOptions {
  intervalMs?: number;
  timeoutMs?: number;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
  signal?: AbortSignal;
}

export interface PollResult<T> {
  value: T;
  settled: boolean;
}

const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function pollUntil<T>(
  read: () => Promise<T>,
  isSettled: (value: T) => boolean,
  opts: PollOptions = {},
): Promise<PollResult<T>> {
  const intervalMs = opts.intervalMs ?? 3000;
  const timeoutMs = opts.timeoutMs ?? 60_000;
  const sleep = opts.sleep ?? defaultSleep;
  const now = opts.now ?? Date.now;
  const deadline = now() + timeoutMs;

  let value = await read();
  while (!isSettled(value)) {
    if (opts.signal?.aborted || now() + intervalMs > deadline) return { value, settled: false };
    await sleep(intervalMs);
    value = await read();
  }
  return { value, settled: true };
}
