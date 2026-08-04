"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, MessageSquare, Play, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/notice";
import { Page, PageHeader, Panel, CardLabel } from "@/components/page";
import { TierMeter } from "@/components/marks";
import { Plume } from "@/components/plume";
import { INPUT_CLS, FIELD_HINT_CLS, FIELD_LABEL_CLS } from "@/lib/ui";
import { cn } from "@/lib/utils";
import {
  deleteFactSheet,
  deleteIntake,
  listFactSheets,
  listOpenIntakes,
  startIntakeForBrand,
  type FactSheetSummary,
  type OpenIntake,
} from "@/lib/api";

/**
 * The landing screen, and it is the CONVERSATION.
 *
 * Everything this product does downstream rests on a fact sheet, and a fact
 * sheet is only worth anything if a human vouched for it — `verification_tier`
 * is the weakest claim on the sheet, and a sheet nobody confirmed can only ever
 * flag low and medium issues. So the first thing on screen is the one action
 * that produces a confirmed sheet: talk to the owner.
 *
 * It used to be the CSV uploader, which put the least valuable path first and
 * left the chat unreachable without a fact-sheet row that only the lead worker
 * or the CLI could create. A client who simply walked in the door could not be
 * onboarded through the UI at all. The uploader still exists, at /runs, for a
 * hand-made question set.
 */
/** The two-step delete both lists use. Armed by the first click, fired by the
 * second — proportionate to an action that is undoable neither way but destroys
 * far less than a project. */
function DeleteButton({
  label,
  armed,
  busy,
  onClick,
}: {
  id: string;
  label: string;
  armed: boolean;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      aria-label={label}
      className={cn(
        "shrink-0 rounded-md px-2 py-1 text-[12px] transition-colors",
        armed ? "bg-navy text-white" : "text-harbour hover:bg-navy/[0.06] hover:text-navy",
      )}
    >
      {busy ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
      ) : armed ? (
        "Confirm"
      ) : (
        <Trash2 className="h-3.5 w-3.5" aria-hidden />
      )}
    </button>
  );
}

export default function StartPage() {
  const router = useRouter();
  const [business, setBusiness] = React.useState("");
  const [website, setWebsite] = React.useState("");
  const [starting, setStarting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [open, setOpen] = React.useState<OpenIntake[]>([]);
  const [active, setActive] = React.useState<FactSheetSummary[]>([]);
  const [confirmDelete, setConfirmDelete] = React.useState<string | null>(null);
  const [deleting, setDeleting] = React.useState<string | null>(null);

  // Two-step: the first click arms, the second deletes.
  const removeSession = async (id: string) => {
    if (confirmDelete !== id) {
      setConfirmDelete(id);
      return;
    }
    setDeleting(id);
    setError(null);
    try {
      await deleteIntake(id);
      setOpen((rows) => rows.filter((r) => r.session_id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not discard that conversation.");
    } finally {
      setDeleting(null);
      setConfirmDelete(null);
    }
  };

  const removeSheet = async (id: string) => {
    if (confirmDelete !== id) {
      setConfirmDelete(id);
      return;
    }
    setDeleting(id);
    setError(null);
    try {
      await deleteFactSheet(id);
      setActive((rows) => rows.filter((r) => r.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete that sheet.");
    } finally {
      setDeleting(null);
      setConfirmDelete(null);
    }
  };

  React.useEffect(() => {
    listOpenIntakes()
      .then(setOpen)
      .catch(() => setOpen([]));
    listFactSheets("active")
      .then(setActive)
      .catch(() => setActive([]));
  }, []);

  const start = async () => {
    if (!business.trim() && !website.trim()) return;
    setStarting(true);
    setError(null);
    try {
      const session = await startIntakeForBrand({ business, website });
      router.push(`/fact-sheets/intake/${encodeURIComponent(session.session_id)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open the intake.");
      setStarting(false);
    }
  };

  return (
    <Page className="gap-6">
      <PageHeader
        eyebrow="Start"
        title="Who are we measuring?"
        helper="Answer a handful of questions about the business and Sable writes the fact sheet, the question set and the run config from what you say. Nothing is guessed — every line comes from an answer you gave."
      />

      {/* --------------------------------------------------- the chat starter */}
      <Panel className="p-6">
        <div className="flex items-start gap-4">
          <span className="mt-0.5 shrink-0">
            <Plume size={30} tone="paper" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[16px] font-semibold leading-tight">
              Start a fact sheet
            </p>
            <p className="mt-1 text-[13px] leading-relaxed text-harbour">
              One of these is enough to begin — the conversation asks for the rest.
            </p>

            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="block">
                <span className={FIELD_LABEL_CLS}>Business name</span>
                <input
                  autoFocus
                  value={business}
                  onChange={(e) => setBusiness(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && void start()}
                  className={cn(INPUT_CLS, "mt-1")}
                />
              </label>
              <label className="block">
                <span className={FIELD_LABEL_CLS}>Website</span>
                <input
                  value={website}
                  onChange={(e) => setWebsite(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && void start()}
                  className={cn(INPUT_CLS, "mt-1")}
                />
                <span className={cn(FIELD_HINT_CLS, "mt-1 block")}>
                  {/* Said plainly, because a blocked or thin site is common and
                      must not read as a failure: the owner's answers are the
                      sheet, and a crawl only ever saves them typing. */}
                  Optional. If we can read the site we&rsquo;ll fill in what we find, but the
                  answers are what count.
                </span>
              </label>
            </div>

            {error ? (
              <Notice tone="problem" className="mt-3">
                {error}
              </Notice>
            ) : null}

            <div className="mt-4 flex items-center gap-3">
              <Button
                variant="hero"
                size="lg"
                onClick={start}
                disabled={starting || (!business.trim() && !website.trim())}
              >
                {starting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                ) : (
                  <MessageSquare className="h-3.5 w-3.5" aria-hidden />
                )}
                Start the conversation
              </Button>
              <Link href="/runs" className="text-[13px] text-blue hover:underline">
                Or upload a question set
              </Link>
            </div>
          </div>
        </div>
      </Panel>

      {/* ------------------------------------------- pick up where you left off */}
      {open.length > 0 ? (
        <Panel>
          <div className="px-5 pb-3 pt-[18px]">
            <CardLabel note={`${open.length} open`}>In progress</CardLabel>
          </div>
          <ul className="divide-y divide-[var(--rule-inner)]">
            {open.map((s) => (
              <li
                key={s.session_id}
                className="flex items-center gap-3 px-5 py-3 hover:bg-navy/[0.03]"
              >
                {/* The link is the row's BODY, not the row — a destructive
                    control inside a navigation link is one mis-tap from
                    discarding the thing you meant to open. */}
                <Link
                  href={`/fact-sheets/intake/${encodeURIComponent(s.session_id)}`}
                  className="flex min-w-0 flex-1 items-center gap-3"
                >
                  <span className="truncate text-[13px] font-medium">{s.business_name}</span>
                  <span className="truncate text-[13px] text-harbour">
                    {s.state === "awaiting_review"
                      ? "ready to review"
                      : `${s.answered} answered`}
                  </span>
                  <ArrowRight className="ml-auto h-4 w-4 shrink-0 text-harbour" aria-hidden />
                </Link>
                <DeleteButton
                  id={s.session_id}
                  label={`Discard the conversation for ${s.business_name}`}
                  armed={confirmDelete === s.session_id}
                  busy={deleting === s.session_id}
                  onClick={() => void removeSession(s.session_id)}
                />
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {/* ------------------------------------------------------- ready to run */}
      {active.length > 0 ? (
        <Panel>
          <div className="px-5 pb-3 pt-[18px]">
            <CardLabel note={`${active.length} approved`}>Ready to run</CardLabel>
          </div>
          <ul className="divide-y divide-[var(--rule-inner)]">
            {active.map((s) => (
              <li key={s.id} className="flex items-center gap-3 px-5 py-3 hover:bg-navy/[0.03]">
                {/* The link is the row's BODY, not the row: a destructive
                    control nested inside a navigation link is one mis-tap from
                    deleting the thing you meant to open. */}
                <Link
                  href={`/runs?sheet=${encodeURIComponent(s.id)}`}
                  className="flex min-w-0 flex-1 items-center gap-3"
                >
                  <TierMeter confirmed={s.verification_tier === "client_confirmed"} />
                  <span className="truncate text-[13px] font-medium">
                    {s.business_name || s.domain}
                  </span>
                  <span className="truncate text-[13px] tabular-nums text-harbour">
                    v{s.version} · {s.domain}
                  </span>
                  <span className="ml-auto inline-flex shrink-0 items-center gap-1.5 text-[13px] text-blue">
                    <Play className="h-3.5 w-3.5" aria-hidden /> Run
                  </span>
                </Link>
                {/* Two-step, because it cannot be undone. Safe for history: a
                    finished run keeps its own copy of the sheet text and the
                    version it was judged against. */}
                <DeleteButton
                  id={s.id}
                  label={`Delete the fact sheet for ${s.business_name || s.domain}`}
                  armed={confirmDelete === s.id}
                  busy={deleting === s.id}
                  onClick={() => void removeSheet(s.id)}
                />
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}
    </Page>
  );
}
