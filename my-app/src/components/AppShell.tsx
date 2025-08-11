import type { ReactNode } from "react";

interface AppShellProps {
  toolbar: ReactNode;
  children: ReactNode;
}

export default function AppShell({ toolbar, children }: AppShellProps) {
  return (
    <div className="app-container">
      <div className="sticky top-0 z-20 border-b bg-background p-4 flex items-center justify-between">{toolbar}</div>
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
