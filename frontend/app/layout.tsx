import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { connection } from "next/server";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Neutral on purpose: the bank's own name is applied from its white-label config at runtime.
export const metadata: Metadata = {
  title: "Online Banking",
  description: "Your money, explained. Figures are calculated by code; the AI only narrates them.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // Render per request so proxy.ts can give every page a fresh CSP nonce.
  await connection();
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col font-sans">{children}</body>
    </html>
  );
}
