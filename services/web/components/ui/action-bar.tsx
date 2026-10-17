import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The one primary action of a screen. On phones it is fixed above the tab bar
 * so it is always in reach (a spacer keeps the content clear of it); from
 * tablet width up it sits in normal flow.
 */
export function ActionBar({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <>
      <div aria-hidden="true" className="h-20 md:hidden" />
      <div
        className={cn(
          "fixed inset-x-0 bottom-[calc(3.25rem+env(safe-area-inset-bottom,0px))] z-20 flex flex-row items-stretch gap-3 border-t-2 border-line bg-panel px-4 py-3 [&>*]:flex-1",
          "md:static md:flex-col md:border-0 md:bg-transparent md:p-0 md:[&>*]:flex-none",
          className,
        )}
        {...props}
      />
    </>
  );
}
