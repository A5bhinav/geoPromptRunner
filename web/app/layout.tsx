import type { Metadata } from "next";
import { Cormorant_Garamond, Inter, Libre_Franklin } from "next/font/google";
import Link from "next/link";
import { Activity } from "lucide-react";
import "./globals.css";
import "../styles/sable.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

// Sable's two faces, self-hosted at build by next/font. Deliberately NOT a CDN
// <link>: that breaks static export, and the PDF worker's header/footer
// templates render in an isolated iframe that cannot reach a relative webfont
// either. Both faces are metrically unlike system-ui — re-measure every print
// layout after a font change rather than assuming the spacing held.
const cormorant = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["300", "400"],
  style: ["normal", "italic"], // italic is for EMPHASIS ONLY, never body copy
  variable: "--font-cormorant",
  display: "swap",
});

const libreFranklin = Libre_Franklin({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-libre-franklin",
  display: "swap",
});

export const metadata: Metadata = {
  title: "GEO Audit",
  description: "Measure how often your brand appears in AI-generated answers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${cormorant.variable} ${libreFranklin.variable}`}
    >
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
              <Link href="/audit" className="text-muted-foreground transition-colors hover:text-foreground">
                Visibility Audit
              </Link>
              <Link href="/fact-sheets" className="text-muted-foreground transition-colors hover:text-foreground">
                Fact sheets
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
