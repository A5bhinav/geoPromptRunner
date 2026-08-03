"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Wordmark } from "@/components/plume";
import { cn } from "@/lib/utils";

/** Nav order is the workflow order: make one → look at them → sell one → the
 * two supporting surfaces. Not alphabetical. */
const NAV = [
  { href: "/", label: "Run" },
  { href: "/projects", label: "Projects" },
  { href: "/teaser", label: "Teaser" },
  { href: "/audit", label: "Deliverable" },
  { href: "/fact-sheets", label: "Fact sheets" },
];

export function AppHeader() {
  const pathname = usePathname();
  return (
    // `on-navy` is what makes Sky resolve — see web/styles/tokens.css. The band
    // is the ONLY place in the app chrome where Sky is legal, and the mark's
    // tallest plume already spends it, so the active nav item below is marked
    // with white + a rule rather than with colour.
    <header className="on-navy no-print sticky top-0 z-30">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-8 px-6">
        {/* Clearspace: the 1u field around the mark is this gap. Nothing enters it. */}
        <Link href="/" aria-label="Sable — home">
          <Wordmark size={20} tone="navy" descriptor="AI SEO" />
        </Link>
        <nav className="ml-auto flex items-center gap-6">
          {NAV.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "border-b-[1.5px] pb-0.5 text-[13px] transition-colors",
                  active
                    ? "border-white text-white"
                    : "border-transparent text-white/70 hover:text-white",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
