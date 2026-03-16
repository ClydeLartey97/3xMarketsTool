import "./globals.css";

import { AppShell } from "@/components/app-shell";
import { ReactNode } from "react";

export const metadata = {
  title: "3x",
  description: "Energy market intelligence for power market operators and traders.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
