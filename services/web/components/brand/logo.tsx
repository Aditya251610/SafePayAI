import { cn } from "@/lib/utils";

interface MarkProps {
  size?: number;
  /** "color" is the full three-plane mark; "mono" uses the current text colour. */
  tone?: "color" | "mono";
  className?: string;
  title?: string;
}

/** The 02A cube: a flat three-plane isometric block. */
export function LogoMark({
  size = 28,
  tone = "color",
  className,
  title = "SafePayAI mark",
}: MarkProps) {
  const mono = tone === "mono";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label={title}
      className={className}
    >
      <polygon points="32,2 60,18 32,34 4,18" fill={mono ? "currentColor" : "var(--fg)"} />
      <polygon
        points="4,18 32,34 32,62 4,46"
        fill={mono ? "currentColor" : "var(--seal)"}
        fillOpacity={mono ? 0.62 : 1}
      />
      <polygon
        points="32,34 60,18 60,46 32,62"
        fill={mono ? "currentColor" : "var(--flare)"}
        fillOpacity={mono ? 0.34 : 1}
      />
      <polyline points="4,18 32,34 60,18" fill="none" stroke="var(--bg)" strokeWidth="1.6" />
      <line x1="32" y1="34" x2="32" y2="62" stroke="var(--bg)" strokeWidth="1.6" />
    </svg>
  );
}

interface LockupProps {
  size?: number;
  className?: string;
}

/** Mark on the left, wordmark with the AI chip on the right. */
export function Logo({ size = 28, className }: LockupProps) {
  return (
    <span className={cn("inline-flex items-center", className)} style={{ gap: size * 0.4 }}>
      <LogoMark size={size} />
      <span className="font-display font-extrabold leading-none" style={{ fontSize: size * 0.72 }}>
        SafePay
        <span
          className="ml-[5px] bg-fg px-[5px] py-[2px] align-middle font-sans font-bold tracking-[0.12em] text-bg"
          style={{ fontSize: size * 0.4 }}
        >
          AI
        </span>
      </span>
    </span>
  );
}
