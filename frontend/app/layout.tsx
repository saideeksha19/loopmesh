import type { Metadata, Viewport } from "next";
import { Inter_Tight, JetBrains_Mono } from "next/font/google";

import "./globals.css";

const interTight = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono-jet",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "LOOPMESH — Industrial Resource Intelligence",
    template: "%s · LOOPMESH",
  },
  description:
    "LOOPMESH discovers industrial resource recovery links through material intelligence, deterministic compatibility rules and explainable matching.",
};

export const viewport: Viewport = {
  themeColor: "#10291A",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body
        className={`${interTight.variable} ${jetbrains.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
