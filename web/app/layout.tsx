import type { Metadata } from "next";
import { Cormorant_Garamond, Libre_Franklin } from "next/font/google";
import "./globals.css";
import "../styles/tokens.css";
import "../styles/sable.css";
import { AppHeader } from "@/components/app-header";

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
      <body className="min-h-screen font-sans antialiased">
        <AppHeader />
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
