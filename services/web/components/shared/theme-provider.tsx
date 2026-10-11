"use client";

import * as React from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

// Light/dark/system theme toggle (REQ-WB-007). next-themes handles the
// no-flash-on-load requirement via a blocking inline script it injects
// itself; attribute="class" pairs with tailwind.config.ts darkMode: "class".
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="system" enableSystem>
      {children}
    </NextThemesProvider>
  );
}
