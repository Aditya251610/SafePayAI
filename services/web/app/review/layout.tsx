import { RoleShell } from "@/components/shell/any-role-shell";

export default function ReviewLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleShell roles={["reviewer"]} desktopOnly>
      {children}
    </RoleShell>
  );
}
