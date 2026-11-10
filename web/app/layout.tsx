import type { Metadata } from "next";
import { Marcellus, Spectral } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";
import { LanguageProvider } from "@/components/ui/LanguageProvider.tsx";
import { SiteFooter } from "@/components/ui/SiteFooter.tsx";
import { SiteNav } from "@/components/ui/SiteNav.tsx";
import { MESSAGES } from "@/lib/i18n.ts";
import { requestLocale } from "@/lib/request-locale.ts";

// Downloaded at build time and served from this app.
const marcellus = Marcellus({ weight: "400", subsets: ["latin"], variable: "--font-marcellus", display: "swap" });
const spectral = Spectral({
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  subsets: ["latin"],
  variable: "--font-spectral",
  display: "swap",
});

export async function generateMetadata(): Promise<Metadata> {
  const t = MESSAGES[await requestLocale()];
  return { title: "Tennis Scouting Analyst", description: t.siteDescription };
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const locale = await requestLocale();
  return (
    <html lang={locale} className={`${marcellus.variable} ${spectral.variable}`}>
      <body>
        <LanguageProvider initial={locale}>
          <SiteNav />
          <div className="site-main">{children}</div>
          <SiteFooter />
        </LanguageProvider>
      </body>
    </html>
  );
}
