"use client";

import * as React from "react";
import { useTheme } from "next-themes";
import { Moon, Sun, Laptop } from "lucide-react";

import { Button } from "@/components/ui/button";

// Light/dark/system theme toggle (REQ-WB-007). Cycles light -> dark ->
// system. No animation beyond the instant icon swap - respects
// prefers-reduced-motion by construction (no transition applied).
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  // Avoid hydration mismatch: next-themes resolves the real theme client-side.
  React.useEffect(() => setMounted(true), []);

  const cycle = () => {
    if (theme === "light") setTheme("dark");
    else if (theme === "dark") setTheme("system");
    else setTheme("light");
  };

  if (!mounted) {
    return <Button variant="ghost" size="icon" aria-label="Toggle theme" disabled />;
  }

  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Laptop;

  return (
    <Button variant="ghost" size="icon" aria-label={`Theme: ${theme}. Click to change.`} onClick={cycle}>
      <Icon className="h-4 w-4" />
    </Button>
  );
}
