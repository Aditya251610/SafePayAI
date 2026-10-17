import { CartView } from "@/components/cart/cart-view";

export const metadata = { title: "Cart · SafePayAI (sandbox demo)" };

export default function CartPage() {
  return (
    <div className="pb-12">
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/cart</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          Cap decided.
          <br />
          <span className="italic text-seal">You approve.</span>
        </h1>
      </div>
      <CartView />
    </div>
  );
}
