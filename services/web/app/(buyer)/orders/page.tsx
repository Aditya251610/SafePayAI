import { OrdersList } from "@/components/orders/orders-list";

export const metadata = { title: "Orders · SafePayAI (sandbox demo)" };

export default function OrdersPage() {
  return (
    <div className="pb-12">
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/orders</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          Your orders.
          <br />
          <span className="italic text-seal">Newest first.</span>
        </h1>
        <p className="mt-4 max-w-xl text-mute">Refunds are merchant-funded via PayPal.</p>
      </div>
      <OrdersList />
    </div>
  );
}
