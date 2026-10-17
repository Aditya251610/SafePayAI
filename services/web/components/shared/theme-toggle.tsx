"use client";

import * as React from "react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

/** Flips between the dark and light boards. Label names the mode it switches to. */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  if (!mounted) return <Button variant="secondary" size="sm" disabled aria-label="Theme" />;

  const toLight = resolvedTheme !== "light";
  return (
    <Button
      variant="secondary"
      size="sm"
      onClick={() => setTheme(toLight ? "light" : "dark")}
      aria-label={toLight ? "Switch to light mode" : "Switch to dark mode"}
    >
      {toLight ? "◐ Light mode" : "◑ Dark mode"}
    </Button>
  );
}
