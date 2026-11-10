import type { Metadata } from "next";
import { Marcellus, Spectral } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";
import { SiteFooter } from "@/components/ui/SiteFooter.tsx";
import { SiteNav } from "@/components/ui/SiteNav.tsx";

// Downloaded at build time and served from this app.
const marcellus = Marcellus({ weight: "400", subsets: ["latin"], variable: "--font-marcellus", display: "swap" });
const spectral = Spectral({
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  subsets: ["latin"],
  variable: "--font-spectral",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Tennis Scouting Analyst",
  description: "Scouting reports on ATP players where every number comes from tested code over public match data.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${marcellus.variable} ${spectral.variable}`}>
      <body>
        <SiteNav />
        <div className="site-main">{children}</div>
        <SiteFooter />
      </body>
    </html>
  );
}
