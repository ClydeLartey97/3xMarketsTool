import "./globals.css";

import { Newsreader } from "next/font/google";
import { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { ThemeProvider } from "@/components/theme-provider";

// Editorial serif for display type only (mastheads, hero headlines, panel
// titles). Body/UI text stays on the native SF Pro stack and numerals stay
// on SF Mono — the serif is the voice, not the interface.
const newsreader = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  weight: ["400", "500", "600"],
  variable: "--font-display",
  display: "swap",
});

export const metadata = {
  title: "3x",
  description: "Energy market intelligence for power market operators and traders.",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={newsreader.variable}>
      <body>
        <ThemeProvider>
          <AppShell>{children}</AppShell>
        </ThemeProvider>
      </body>
    </html>
  );
}
