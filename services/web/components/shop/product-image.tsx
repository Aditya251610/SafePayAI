"use client";

import * as React from "react";

import { PLACEHOLDER_IMAGE, productImage } from "@/lib/shop/catalog";
import { cn } from "@/lib/utils";

/** Static 640x480 picture with reserved space (no layout shift) and one fallback to the placeholder. */
export function ProductImage({
  sku,
  alt = "",
  className,
  priority = false,
}: {
  sku: string;
  alt?: string;
  className?: string;
  priority?: boolean;
}) {
  const [src, setSrc] = React.useState(productImage(sku));
  React.useEffect(() => setSrc(productImage(sku)), [sku]);
  return (
    // Plain static file: nothing to optimise, and the size is fixed by width/height.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      width={640}
      height={480}
      loading={priority ? "eager" : "lazy"}
      decoding="async"
      onError={() => setSrc((cur) => (cur === PLACEHOLDER_IMAGE ? cur : PLACEHOLDER_IMAGE))}
      className={cn("aspect-[4/3] h-auto w-full bg-panel object-cover", className)}
    />
  );
}
