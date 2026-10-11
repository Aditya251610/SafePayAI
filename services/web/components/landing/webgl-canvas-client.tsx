"use client";

import dynamic from "next/dynamic";

// `ssr: false` requires a Client Component boundary - this file exists only
// to hold that boundary so app/page.tsx itself can stay a Server Component.
// See components/landing/webgl-canvas.tsx for the actual effect and its
// risk mitigations (tech-stack.md T1/T2/T3).
const WebglCanvas = dynamic(
  () => import("@/components/landing/webgl-canvas").then((m) => m.WebglCanvas),
  { ssr: false },
);

export default WebglCanvas;
