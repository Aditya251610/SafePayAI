"use client";

import { motion } from "framer-motion";

/**
 * One Aceternity-style animated component for the landing hook moment
 * (tech-stack.md sec 3.1, spec.md sec 10 WHERE rule). Wave 4: a
 * self-contained "spotlight/gradient text reveal" built with Framer Motion
 * only, matching the visual language Aceternity UI primitives use, without
 * pulling in the full Aceternity package yet (tech-stack.md T4: "cherry-pick
 * only the specific components used... do not adopt the library wholesale").
 *
 * Wave 5 may replace the motion.div below with an actual Aceternity
 * component (e.g. their spotlight/text-generate-effect primitive) - the
 * contract (landing-only, client rendered, respects prefers-reduced-motion
 * via Framer Motion's built-in support) stays the same.
 */
export function AceternityHero({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="relative z-10 flex flex-col items-center gap-4 text-center">
      <motion.h1
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="bg-gradient-to-b from-white to-neutral-400 bg-clip-text text-4xl font-bold text-transparent sm:text-6xl"
      >
        {title}
      </motion.h1>
      <motion.p
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.15, ease: "easeOut" }}
        className="max-w-xl text-base text-neutral-300 sm:text-lg"
      >
        {subtitle}
      </motion.p>
    </div>
  );
}
