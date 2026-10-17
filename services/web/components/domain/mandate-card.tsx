import Link from "next/link";

import { Meter } from "@/components/ui/meter";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import type { Mandate } from "@/lib/api/schemas/mandate";
import { formatDate } from "@/lib/format/date";
import { mandateStatusLabel, shortId } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";

export function mandateTone(status: string) {
  if (status === "active") return "solid-ret" as const;
  if (status === "revoked") return "flare" as const;
  return "neutral" as const;
}

/** One mandate on the buyer home. Figures are the server's, shown as given. */
export function MandateCard({ mandate }: { mandate: Mandate }) {
  return (
    <Slab className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tag tone={mandateTone(mandate.status)}>{mandateStatusLabel(mandate.status)}</Tag>
        <Link
          href={`/mandate/${mandate.mandate_id}`}
          className="font-mono text-xs text-seal underline-offset-4 hover:underline"
        >
          MND-{shortId(mandate.mandate_id, 6)}
        </Link>
      </div>
      <p className="text-lg font-semibold">{mandate.intent_text}</p>
      <div>
        <p className="tabular text-sm text-mute">
          <span className="font-semibold text-fg">
            {formatMoney(mandate.spent_minor, mandate.currency)}
          </span>{" "}
          of {formatMoney(mandate.max_total_minor, mandate.currency)}
        </p>
        <Meter
          className="mt-2"
          part={mandate.spent_minor}
          whole={mandate.max_total_minor}
          extra={mandate.reserved_minor}
          label={`Spent ${formatMoney(mandate.spent_minor, mandate.currency)} of ${formatMoney(mandate.max_total_minor, mandate.currency)}`}
        />
      </div>
      <p className="text-sm text-dim">
        {mandate.merchant_allowlist.map((m) => m.display_name).join(" · ")} · ends{" "}
        {formatDate(mandate.expires_at)}
      </p>
    </Slab>
  );
}
