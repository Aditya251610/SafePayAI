/**
 * (buyer) route group layout.
 *
 * REQ-WB-013: any role check here is UI convenience only - the gateway is
 * authoritative and denies server-side regardless of what the client shows.
 * TODO Wave 5: redirect to /session-ended on a missing/expired session, and
 * to the merchant equivalent if a merchant session hits a buyer route (the
 * server would deny anyway, but hiding it client-side avoids a confusing
 * flash of buyer UI).
 */
export default function BuyerLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
