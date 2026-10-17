import { RoleShell } from "@/components/shell/any-role-shell";

export default function MerchantLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleShell roles={["merchant", "operator"]} desktopOnly>
      {children}
    </RoleShell>
  );
}
