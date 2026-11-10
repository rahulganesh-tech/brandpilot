"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { IssueNote, type DecisionPayload } from "@/components/IssueNote";
import { Proof } from "@/components/Proof";
import { StatusBadge } from "@/components/StatusBadge";
import { useWorkspace } from "@/components/Workspace";
import { api, send, when } from "@/lib/api";
import type { ScanBundle } from "@/lib/types";

const AI_NOTE: Record<string, string> = {
  ok: "Checked with brand rules and AI (claims vs approved facts, tone vs voice guide).",
  partial: "Some AI checks couldn’t run this time. Brand rules and the other AI checks were applied.",
  error: "AI checks couldn’t run this time. Brand rules were still applied. To retry, choose Rewrite, then Save and check again.",
  off: "Checked with brand rules. AI checks are off on this server.",
};

export default function ScanPage() {
  const { id } = useParams<{ id: string }>();
  const { role, person } = useWorkspace();
  const [bundle, setBundle] = useState<ScanBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [rewriting, setRewriting] = useState(false);
  const [draft, setDraft] = useState("");
  const [comment, setComment] = useState("");
  const [copied, setCopied] = useState(false);
  const noteRefs = useRef(new Map<string, HTMLLIElement>());

  useEffect(() => {
    api<ScanBundle>(`/scans/${id}`).then(setBundle).catch((e: Error) => setLoadError(e.message));
  }, [id]);

  const run = useCallback(async (fn: () => Promise<ScanBundle>) => {
    setBusy(true);
    setError(null);
    try {
      setBundle(await fn());
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  const open = useMemo(
    () => (bundle?.issues ?? []).filter((i) => i.decision === "open").sort((a, b) => a.span_start - b.span_start),
    [bundle],
  );
  const resolved = useMemo(() => (bundle?.issues ?? []).filter((i) => i.decision !== "open"), [bundle]);
  const numbers = useMemo(() => new Map(open.map((i, n) => [i.id, n + 1])), [open]);

  if (loadError) {
    return (
      <p role="alert" className="text-high">
        {loadError}. <Link href="/" className="text-accent underline">Back to Write & check</Link>
      </p>
    );
  }
  if (!bundle) return <p className="text-muted">Loading…</p>;

  const { scan, versions, reviews } = bundle;
  const editable = scan.status === "draft" || scan.status === "sent_back";
  const reviewing = scan.status === "in_review" && role === "manager";
  const canDecide = editable || reviewing;
  const blocking = open.filter((i) => !i.needs_human).length;
  const lastReview = reviews.at(-1);

  function select(issueId: string) {
    setActiveId(issueId);
    noteRefs.current.get(issueId)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function decide(issueId: string, p: DecisionPayload) {
    run(() => send<ScanBundle>(`/issues/${issueId}`, "PATCH", { ...p, author: person }));
  }

  const timeline = [
    ...versions.map((v) => ({ at: v.created_at, key: v.id, text: `Version ${v.number}: ${v.note}`, who: v.created_by })),
    ...reviews.map((r) => ({
      at: r.created_at,
      key: r.id,
      text: r.action === "approve" ? `Approved${r.comment ? `: “${r.comment}”` : ""}` : `Sent back: “${r.comment}”`,
      who: r.reviewer,
    })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/" className="text-sm text-accent hover:underline">
          Write & check
        </Link>
        <span className="text-muted" aria-hidden>/</span>
        <span className="text-sm text-muted">{scan.channel.charAt(0).toUpperCase() + scan.channel.slice(1)} draft</span>
        <StatusBadge status={scan.status} />
        <span className="ml-auto text-sm text-muted">
          by {scan.author} · {when(scan.created_at)}
        </span>
      </div>

      {scan.status === "approved" && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-ok/40 bg-[#eef8f0] px-4 py-3">
          <p className="font-medium text-ok">Approved by {lastReview?.reviewer ?? "a manager"}. Ready to publish.</p>
          <button
            type="button"
            className="btn btn-ok ml-auto"
            onClick={() => {
              navigator.clipboard?.writeText(scan.content).then(() => setCopied(true), () => setCopied(false));
            }}
          >
            {copied ? "Copied" : "Copy approved text"}
          </button>
        </div>
      )}
      {scan.status === "sent_back" && lastReview && (
        <div className="mt-4 rounded-lg border border-high/40 bg-[#fdf1f5] px-4 py-3">
          <p className="font-medium text-high">Sent back by {lastReview.reviewer}</p>
          <p className="mt-1">“{lastReview.comment}”</p>
        </div>
      )}
      {scan.status === "in_review" && role === "creator" && (
        <p className="mt-4 rounded-lg border border-rule bg-paper px-4 py-3 text-muted">
          Waiting for a manager to review. Switch “Viewing as” to Manager to review it yourself.
        </p>
      )}

      <div className="mt-6 grid gap-8 lg:grid-cols-[minmax(0,1fr)_380px]">
        <section>
          <div className="rounded-xl border border-rule bg-paper px-6 py-6 shadow-[0_1px_0_#d9dce4,0_12px_32px_-18px_rgba(27,31,59,0.35)] sm:px-10 sm:py-9">
            {scan.has_image && (
              <figure className="mb-6">
                <img
                  src={`/api/scans/${scan.id}/image`}
                  alt="The uploaded design"
                  className="max-h-[480px] w-auto rounded-lg border border-rule"
                />
                <figcaption className="mt-3 text-sm text-muted">
                  {scan.content.trim()
                    ? "Text found in the image. Fixes here give the designer the corrected copy."
                    : "No text found in this image."}
                </figcaption>
              </figure>
            )}
            {rewriting ? (
              <>
                <label htmlFor="rewrite" className="sr-only">Rewrite the draft</label>
                <textarea
                  id="rewrite"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={8}
                  className="proof w-full resize-y outline-none"
                  autoFocus
                />
              </>
            ) : (
              <Proof content={scan.content} issues={open} numbers={numbers} activeId={activeId} onSelect={select} />
            )}
          </div>

          {error && (
            <p role="alert" className="mt-3 text-sm text-high">
              {error}
            </p>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {editable && !rewriting && (
              <>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy || blocking > 0}
                  onClick={() => run(() => send<ScanBundle>(`/scans/${scan.id}/submit`, "POST"))}
                >
                  Submit for review
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={busy}
                  onClick={() => {
                    setDraft(scan.content);
                    setRewriting(true);
                  }}
                >
                  Rewrite
                </button>
                <span className="text-sm text-muted">
                  {blocking > 0
                    ? `Resolve ${blocking} more ${blocking === 1 ? "issue" : "issues"} to submit.`
                    : open.length > 0
                      ? "Remaining issues will go to the reviewer."
                      : "All clear."}
                </span>
              </>
            )}
            {rewriting && (
              <>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy || !draft.trim()}
                  onClick={async () => {
                    const ok = await run(() =>
                      send<ScanBundle>(`/scans/${scan.id}/content`, "PUT", { content: draft, author: person }),
                    );
                    if (ok) setRewriting(false);
                  }}
                >
                  {busy ? "Checking…" : "Save and check again"}
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setRewriting(false)}>
                  Cancel
                </button>
              </>
            )}
          </div>

          {reviewing && (
            <div className="mt-6 rounded-xl border border-rule bg-paper p-5">
              <h2 className="font-semibold">Your review</h2>
              <p className="mt-1 text-sm text-muted">
                {open.length > 0
                  ? `Decide the ${open.length} flagged ${open.length === 1 ? "item" : "items"} on the right before approving.`
                  : "Every flag has been decided."}
              </p>
              <label htmlFor="comment" className="mt-3 block text-sm text-muted">
                Comment for the creator (required to send back)
              </label>
              <textarea id="comment" className="field mt-1" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn btn-ok"
                  disabled={busy || open.length > 0}
                  onClick={() =>
                    run(() => send<ScanBundle>(`/scans/${scan.id}/review`, "POST", { action: "approve", comment, reviewer: person }))
                  }
                >
                  Approve
                </button>
                <button
                  type="button"
                  className="btn btn-warn"
                  disabled={busy || comment.trim().length < 3}
                  onClick={() =>
                    run(() => send<ScanBundle>(`/scans/${scan.id}/review`, "POST", { action: "send_back", comment, reviewer: person }))
                  }
                >
                  Send back
                </button>
              </div>
            </div>
          )}

          <section className="mt-10">
            <h2 className="text-sm font-semibold text-muted">History</h2>
            <ol className="mt-3 space-y-2 border-l-2 border-rule pl-4">
              {timeline.map((t) => (
                <li key={t.key} className="text-sm">
                  <span className="font-medium">{t.text}</span>
                  <span className="text-muted"> — {t.who}, {when(t.at)}</span>
                </li>
              ))}
            </ol>
          </section>
        </section>

        <aside aria-label="Issues">
          <h2 className="text-sm font-semibold text-muted">
            {open.length === 0 ? "No open issues" : `${open.length} open ${open.length === 1 ? "issue" : "issues"}`}
          </h2>
          <p className="mt-1 text-xs text-muted">{AI_NOTE[scan.ai_status] ?? AI_NOTE.off}</p>
          {open.length === 0 && resolved.length === 0 && (
            <p className="mt-3 rounded-lg border border-rule bg-paper px-4 py-3 text-sm">
              Nothing in this draft breaks a brand rule. Submit it for review when you’re ready.
            </p>
          )}
          <ul className="mt-3 space-y-3">
            {open.map((i) => (
              <IssueNote
                key={i.id}
                ref={(el) => {
                  if (el) noteRefs.current.set(i.id, el);
                  else noteRefs.current.delete(i.id);
                }}
                issue={i}
                number={numbers.get(i.id)}
                active={activeId === i.id}
                locked={!canDecide}
                busy={busy}
                onSelect={() => setActiveId(i.id)}
                onDecide={(p) => decide(i.id, p)}
              />
            ))}
          </ul>
          {resolved.length > 0 && (
            <details className="mt-6">
              <summary className="cursor-pointer text-sm font-semibold text-muted">Resolved ({resolved.length})</summary>
              <ul className="mt-3 space-y-2">
                {resolved.map((i) => (
                  <IssueNote
                    key={i.id}
                    issue={i}
                    active={false}
                    locked={!canDecide}
                    busy={busy}
                    onSelect={() => undefined}
                    onDecide={(p) => decide(i.id, p)}
                  />
                ))}
              </ul>
            </details>
          )}
        </aside>
      </div>
    </div>
  );
}
