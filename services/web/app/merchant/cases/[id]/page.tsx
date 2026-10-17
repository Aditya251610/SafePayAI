import { MerchantCase } from "@/components/merchant/merchant-case";

export const metadata = { title: "Merchant case · SafePayAI (sandbox demo)" };

export default function MerchantCasePage() {
  return (
    <div className="pt-10 md:pt-12">
      <MerchantCase />
    </div>
  );
}
