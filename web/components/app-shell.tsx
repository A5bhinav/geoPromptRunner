"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileText, FolderClosed, MessageSquare, Play } from "lucide-react";
import { Wordmark } from "@/components/plume";
import { cn } from "@/lib/utils";

/**
 * The app chrome: a 240px navy rail and everything else.
 *
 * WHY A SIDEBAR REPLACED THE TOP BAND. The band gave every screen a 56px navy
 * stripe and then centred the work in `max-w-6xl`, which is fine for a marketing
 * page and wrong for this: the report is four full-bleed panels, the run screen
 * is a two-column workbench, and both were being squeezed into 1152px with dead
 * margin either side. The rail spends the same navy vertically, where it costs
 * nothing horizontally, and gives the three surfaces that need it (report
 * sections, sheet list, live progress) a permanent home that does not push the
 * work down the page.
 *
 * `on-navy` is what makes Sky resolve at all (see styles/tokens.css) and this
 * rail is the only place in the app chrome that carries it. The mark's tallest
 * plume already spends Sky, so the ACTIVE NAV ITEM is marked with white + an
 * inset white rule rather than with colour — one bright note per screen, and it
 * is already spent.
 */

/** Nav order is the ORDER OF THE WORK: start a conversation → the sheet it
 * produces → run against that sheet → read the results. Not alphabetical, and
 * not by how often a screen is opened.
 *
 * THREE ITEMS, AND THAT IS THE WHOLE RAIL. `/teaser` and `/audit` are still real
 * routes and still work — the project detail page links straight into
 * `/teaser?teaser=…`, which is how you reach a teaser you already made. They are
 * not in the rail because the rail is the run → report loop and neither is a
 * step in it; a permanent nav slot for a surface you visit from somewhere else
 * spends the rail's attention on the wrong thing. */
const NAV = [
  // Start is FIRST and is the landing route. Everything downstream rests on a
  // fact sheet, and a sheet is only worth anything if a human vouched for it —
  // so the conversation that produces one is the front door, not a thing you
  // find after uploading a CSV.
  { href: "/", label: "Start", Icon: MessageSquare, exact: true },
  { href: "/fact-sheets", label: "Fact sheets", Icon: FileText },
  { href: "/runs", label: "Runs", Icon: Play },
  { href: "/projects", label: "Projects", Icon: FolderClosed },
];

const ITEM_CLS =
  "flex items-center gap-[11px] rounded-lg px-2.5 py-2.5 text-[13.5px] transition-colors";

function NavItem({
  href,
  label,
  Icon,
  active,
}: {
  href: string;
  label: string;
  Icon: typeof Play;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        ITEM_CLS,
        active
          ? "bg-white/10 font-medium text-white shadow-[inset_2px_0_0_#fff]"
          : "text-white/70 hover:bg-white/[0.06] hover:text-white",
      )}
    >
      <Icon className="h-[15px] w-[15px] shrink-0" aria-hidden />
      {label}
    </Link>
  );
}

/**
 * Per-page content injected into the rail — the report's SECTIONS list, the
 * intake's SHEETS list, the live progress readout in the footer.
 *
 * A portal rather than context: the rail is rendered once by the root layout and
 * the page that owns the content is three levels down and client-side. Context
 * would mean a setState-in-effect on every page and a render of the whole shell
 * each time a page's own state changed. The portal writes straight into the DOM
 * node and re-renders only its own subtree.
 */
export function SidebarSlot({
  slot,
  children,
}: {
  slot: "sections" | "footer";
  children: React.ReactNode;
}) {
  const [host, setHost] = React.useState<HTMLElement | null>(null);
  // After mount only — the node does not exist during SSR, and rendering the
  // portal on the server would duplicate the content into the page body.
  React.useEffect(() => setHost(document.getElementById(`sidebar-${slot}`)), [slot]);
  return host ? createPortal(children, host) : null;
}

/** The label above a rail list. Faint on navy — it is a signpost, not content. */
export function SidebarLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 ml-2.5 text-[9px] font-semibold uppercase tracking-[0.32em] text-white/45">
      {children}
    </p>
  );
}

/** One row in a rail list (report sections, sheets). Rendered as a button when
 * it acts on the page, as a link when it navigates. */
export function SidebarRow({
  active,
  count,
  children,
  ...props
}: {
  active?: boolean;
  count?: number | string;
  children: React.ReactNode;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-[12.5px] transition-colors",
        active ? "bg-white/10 text-white" : "text-white/70 hover:bg-white/[0.06] hover:text-white",
      )}
      {...props}
    >
      <span className="truncate">{children}</span>
      {count !== undefined ? (
        <span className="ml-2 shrink-0 tabular-nums text-white/45">{count}</span>
      ) : null}
    </button>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname.startsWith(href);

  return (
    <div className="flex min-h-screen">
      {/* `no-print`: the PDF worker renders /audits/[id]?mode=print through this
          same layout, and a navy rail down the left of page 1 of a client
          deliverable is not a thing anyone would ship. */}
      <aside className="on-navy no-print sticky top-0 flex h-screen w-60 shrink-0 flex-col">
        {/* Clearspace: the 1u field around the mark is this padding. Nothing
            enters it — not a version chip, not a client switcher. */}
        <div className="px-5 pb-5 pt-[22px]">
          <Link href="/" aria-label="Sable — home">
            <Wordmark size={22} tone="navy" />
          </Link>
        </div>

        <nav className="flex flex-col gap-px px-3">
          {NAV.map((item) => (
            <NavItem key={item.href} {...item} active={isActive(item.href, item.exact)} />
          ))}
        </nav>

        {/* Page-owned. Empty on most screens, and an empty div costs nothing. */}
        <div id="sidebar-sections" className="mt-[22px] min-h-0 overflow-y-auto px-3" />

        {/* Also page-owned, but the border is the shell's so it renders whether
            or not a page fills it — the rail should not lose its foot. */}
        <div
          id="sidebar-footer"
          className="mt-auto border-t border-white/[0.14] p-4 empty:border-t-0"
        />
      </aside>

      {/* min-w-0 is load-bearing: without it a wide table inside a flex child
          refuses to shrink and the whole page scrolls sideways. */}
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
