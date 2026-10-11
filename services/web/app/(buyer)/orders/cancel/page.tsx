/**
 * /orders/cancel - neutral cancel screen (spec.md sec 2.7). Plain shadcn
 * only, no logic needed beyond static copy.
 */
export default function OrderCancelPage() {
  return (
    <div className="mx-auto flex min-h-[50vh] max-w-md flex-col items-center justify-center px-4 text-center">
      <p className="text-sm text-muted-foreground">Checkout cancelled, nothing was charged.</p>
    </div>
  );
}
