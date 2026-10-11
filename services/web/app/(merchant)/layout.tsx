/**
 * (merchant) route group layout.
 *
 * REQ-WB-013: any role check here is UI convenience only - the gateway is
 * authoritative. TODO Wave 5: redirect to the shared merchant login (or
 * /session-ended) if no merchant session is present.
 */
export default function MerchantLayout({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto w-full max-w-6xl px-4 py-8">{children}</div>;
}
