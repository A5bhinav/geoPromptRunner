import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import { Activity } from "lucide-react";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "GEO Audit",
  description: "Measure how often your brand appears in AI-generated answers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen font-sans antialiased">
        <header className="no-print sticky top-0 z-30 border-b bg-card/80 backdrop-blur">
          <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Activity className="h-4 w-4" />
              </span>
              GEO Audit
            </Link>
            <span className="ml-2 text-sm text-muted-foreground">
              AI visibility measurement
            </span>
            <nav className="ml-auto flex items-center gap-4 text-sm">
              <Link href="/" className="text-muted-foreground transition-colors hover:text-foreground">
                Audit
              </Link>
              <Link href="/projects" className="text-muted-foreground transition-colors hover:text-foreground">
                Projects
              </Link>
              <Link href="/teaser" className="text-muted-foreground transition-colors hover:text-foreground">
                Teaser
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
