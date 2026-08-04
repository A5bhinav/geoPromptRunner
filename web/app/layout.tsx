import type { Metadata } from "next";
import { Cormorant_Garamond, Libre_Franklin } from "next/font/google";
import "./globals.css";
import "../styles/tokens.css";
import "../styles/motion.css";
import "../styles/sable.css";
// The white-label skin. Loaded alongside Sable rather than swapped at build
// time: both are scoped to a class, the report picks one via brand.themeClass,
// and shipping only the "active" one would make the second skin something
// nobody ever renders — which is how it stayed a stub for a whole phase.
import "../styles/neutral.css";
import { AppShell } from "@/components/app-shell";

// Sable's two faces, self-hosted at build by next/font. Deliberately NOT a CDN
// <link>: that breaks static export, and the PDF worker's header/footer
// templates render in an isolated iframe that cannot reach a relative webfont
// either. Both faces are metrically unlike system-ui — re-measure every print
// layout after a font change rather than assuming the spacing held.
//
// Inter is GONE. Libre Franklin is the UI face per the guide; a third face was
// 40KB serving nothing.
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
  title: "Sable — AI visibility",
  description: "Measure how often your brand appears in AI-generated answers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${cormorant.variable} ${libreFranklin.variable}`}>
      {/* The shell owns the page's outer geometry now; the content well and its
          padding belong to each page's own <Page>, because the report and the
          intake both need to break out of it (full-bleed panels, a full-height
          composer column) and a padded <main> would have to be fought. */}
      <body className="min-h-screen font-sans antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
