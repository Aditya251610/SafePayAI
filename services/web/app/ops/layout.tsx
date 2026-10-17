import { RoleShell } from "@/components/shell/any-role-shell";

export default function OpsLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleShell roles={["operator"]} desktopOnly>
      {children}
    </RoleShell>
  );
}
