import { AnyRoleShell } from "@/components/shell/any-role-shell";

export default function AuditLayout({ children }: { children: React.ReactNode }) {
  return <AnyRoleShell>{children}</AnyRoleShell>;
}
