import { notFound } from "next/navigation";

import { Slab } from "@/components/ui/slab";
import { KNOWN_ERROR_CODES, errorCopy } from "@/lib/api/messages";

export const metadata = { title: "States · SafePayAI (sandbox demo)" };

/** Review page for every error message. Not served in production builds. */
export default function StatesPage() {
  if (process.env.NODE_ENV === "production" && process.env.NEXT_PUBLIC_PS_WEB_STATES !== "true") {
    notFound();
  }
  return (
    <div className="mx-auto max-w-page px-4 py-10 md:px-10">
      <h1 className="font-display text-4xl font-black">System states</h1>
      <p className="mt-2 text-mute">
        Every error code the screens handle, with the text people see.
      </p>
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {KNOWN_ERROR_CODES.map((code) => {
          const c = errorCopy(code);
          return (
            <Slab key={code}>
              <p className="font-mono text-xs text-seal">{code}</p>
              <p className="mt-2 font-semibold">{c.title}</p>
              <p className="mt-1 text-sm text-mute">{c.text}</p>
              {c.retryable && <p className="mt-2 text-xs text-dim">Offers a retry</p>}
            </Slab>
          );
        })}
      </div>
    </div>
  );
}
