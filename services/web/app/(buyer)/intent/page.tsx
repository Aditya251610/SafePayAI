import { Suspense } from "react";

import { IntentPage } from "@/components/intent/intent-page";

export const metadata = { title: "Shop · SafePayAI (sandbox demo)" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <IntentPage />
    </Suspense>
  );
}
