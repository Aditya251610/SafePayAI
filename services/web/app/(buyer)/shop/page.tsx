import { ShopView } from "@/components/shop/shop-view";

export const metadata = { title: "Shop · SafePayAI (sandbox demo)" };

export default function ShopPage() {
  return (
    <div className="pb-24">
      <div className="pb-8 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/shop</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          Browse the shelves.
          <br />
          <span className="italic text-seal">Server checks the cart.</span>
        </h1>
        <p className="mt-4 max-w-2xl text-mute">
          Add items yourself instead of describing them. Your mandate still decides whether the cart
          goes ahead.
        </p>
      </div>
      <ShopView />
    </div>
  );
}
