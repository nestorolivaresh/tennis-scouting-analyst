import type { Metadata } from "next";
import { Archivo, Newsreader } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

// Archivo's width axis gives condensed, scoreboard-like names and numbers; Newsreader sets
// the written report. Both are downloaded at build time and served from this app.
const sans = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-sans", display: "swap" });
const serif = Newsreader({ subsets: ["latin"], variable: "--font-serif", display: "swap" });

export const metadata: Metadata = {
  title: "Tennis Scouting Analyst",
  description: "Scouting reports on ATP players where every number comes from tested code over public match data.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body>{children}</body>
    </html>
  );
}
