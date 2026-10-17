import type { z } from "zod";
import { ApiError } from "../errors";

/** Validate a request body before it leaves the browser. */
export function parseBody<T>(schema: z.ZodType<T>, input: unknown): T {
  const result = schema.safeParse(input);
  if (result.success) return result.data;
  throw new ApiError({
    code: "VALIDATION_ERROR",
    message: "Some fields need attention.",
    status: 0,
    fields: result.error.issues.map((i) => ({
      field: i.path.join("."),
      message: i.message,
    })),
  });
}
