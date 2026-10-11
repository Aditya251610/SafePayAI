"use client";

import * as React from "react";

/**
 * Minimal working WebGL canvas for the landing/hook moment only
 * (tech-stack.md sec 3.1/3.2 WHERE rule, spec.md sec 10). Never imported by
 * any money-path route.
 *
 * Wave 4: a small working raw-WebGL gradient/particle-field shader - enough
 * to prove the effect works end to end (feature-detect + fallback,
 * client-only render, cleans up its own GL context). Wave 5 may swap this
 * for an Aceternity-bundled primitive or react-three-fiber (tech-stack.md
 * leaves the exact library to implementation) without changing the
 * contract: a client-only, ssr:false component that degrades gracefully.
 *
 * Risk mitigations applied (tech-stack.md T1/T3):
 *   - `prefers-reduced-motion` -> render the static CSS-gradient fallback,
 *     never start the animation loop.
 *   - WebGL context unavailable/lost -> fallback to the same static
 *     gradient `<div>` instead of a blank canvas.
 *   - Client-only: this component must only ever be loaded via
 *     `dynamic(() => import(...), { ssr: false })` from app/page.tsx, so it
 *     never participates in SSR/hydration of the authenticated app shell.
 */
export function WebglCanvas() {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  const [supported, setSupported] = React.useState(true);

  React.useEffect(() => {
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion) {
      setSupported(false);
      return;
    }

    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("webgl") ?? canvas.getContext("experimental-webgl");
    if (!ctx || !(ctx instanceof WebGLRenderingContext)) {
      setSupported(false);
      return;
    }
    // Re-bind to a const with the narrowed type - TS control-flow narrowing
    // of `ctx` does not survive into the nested `compile`/`frame` closures
    // below otherwise.
    const gl: WebGLRenderingContext = ctx;

    let raf = 0;
    let lost = false;
    const onContextLost = (e: Event) => {
      e.preventDefault();
      lost = true;
      setSupported(false);
    };
    canvas.addEventListener("webglcontextlost", onContextLost, false);

    const resize = () => {
      canvas.width = canvas.clientWidth;
      canvas.height = canvas.clientHeight;
      gl.viewport(0, 0, canvas.width, canvas.height);
    };
    resize();
    window.addEventListener("resize", resize);

    // Tiny fragment-shader gradient animation - deliberately simple (no
    // geometry/buffers beyond a full-screen triangle) so Wave 4 proves the
    // WebGL pipeline works without pulling in a 3D library yet.
    const vertSrc = `
      attribute vec2 position;
      void main() { gl_Position = vec4(position, 0.0, 1.0); }
    `;
    const fragSrc = `
      precision mediump float;
      uniform float uTime;
      uniform vec2 uResolution;
      void main() {
        vec2 uv = gl_FragCoord.xy / uResolution;
        vec3 color = 0.5 + 0.5 * cos(uTime * 0.3 + uv.xyx * 4.0 + vec3(0.0, 2.0, 4.0));
        gl_FragColor = vec4(color * 0.6, 1.0);
      }
    `;

    function compile(type: number, src: string) {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, src);
      gl.compileShader(shader);
      return shader;
    }

    const program = gl.createProgram()!;
    gl.attachShader(program, compile(gl.VERTEX_SHADER, vertSrc));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fragSrc));
    gl.linkProgram(program);
    gl.useProgram(program);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      gl.STATIC_DRAW,
    );
    const posLoc = gl.getAttribLocation(program, "position");
    gl.enableVertexAttribArray(posLoc);
    gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

    const timeLoc = gl.getUniformLocation(program, "uTime");
    const resLoc = gl.getUniformLocation(program, "uResolution");

    const start = performance.now();
    const frame = () => {
      if (lost) return;
      gl.uniform1f(timeLoc, (performance.now() - start) / 1000);
      gl.uniform2f(resLoc, canvas.width, canvas.height);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      raf = requestAnimationFrame(frame);
    };
    frame();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      canvas.removeEventListener("webglcontextlost", onContextLost);
    };
  }, []);

  if (!supported) {
    // Static fallback: CSS gradient, no WebGL, no motion.
    return (
      <div
        aria-hidden
        className="h-full w-full bg-gradient-to-br from-indigo-500 via-purple-500 to-amber-400"
      />
    );
  }

  return <canvas ref={canvasRef} aria-hidden className="h-full w-full" />;
}
