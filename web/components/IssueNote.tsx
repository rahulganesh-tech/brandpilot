"use client";

import { forwardRef, useState } from "react";
import { SEVERITY_LABEL } from "@/lib/api";
import type { Issue } from "@/lib/types";

export type DecisionPayload =
  | { decision: "accepted" }
  | { decision: "edited"; edited_text?: string }
  | { decision: "ignored"; reason: string }
  | { decision: "open" };

interface Props {
  issue: Issue;
  number?: number;
  active: boolean;
  locked: boolean;
  busy: boolean;
  onSelect: () => void;
  onDecide: (p: DecisionPayload) => void;
}

const DONE_LABEL = { accepted: "Fix accepted", edited: "Edited", ignored: "Ignored", open: "" };

export const IssueNote = forwardRef<HTMLLIElement, Props>(function IssueNote(
  { issue, number, active, locked, busy, onSelect, onDecide },
  ref,
) {
  const [mode, setMode] = useState<"idle" | "edit" | "ignore">("idle");
  const [text, setText] = useState(issue.fix ?? issue.excerpt);
  const [reason, setReason] = useState("");
  const open = issue.decision === "open";
  const inImage = issue.span_start < 0;

  if (!open) {
    return (
      <li ref={ref} className="rounded-lg border border-rule bg-paper/60 px-4 py-3 text-sm">
        <div className="flex items-center gap-2">
          <span className={issue.decision === "ignored" ? "font-semibold text-muted" : "font-semibold text-ok"}>
            {DONE_LABEL[issue.decision]}
          </span>
          <span className="text-muted">
            {issue.type} · {issue.source_code}
          </span>
          {issue.decision === "ignored" && !locked && (
            <button
              type="button"
              disabled={busy}
              onClick={() => onDecide({ decision: "open" })}
              className="ml-auto text-accent hover:underline"
            >
              Reopen
            </button>
          )}
        </div>
        <p className="mt-1 text-muted">
          <span className={issue.span_start < 0 ? "" : "line-through"}>{issue.excerpt}</span>
          {issue.decision_reason && <> — {issue.decision_reason}</>}
        </p>
      </li>
    );
  }

  return (
    <li
      ref={ref}
      onClick={onSelect}
      className={`rounded-lg border bg-paper px-4 py-4 transition-shadow ${
        active ? "border-ink shadow-[0_8px_24px_-14px_rgba(27,31,59,0.6)]" : "border-rule"
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 text-xs font-bold sev-text-${issue.severity}`}
          style={{ borderColor: "currentColor" }}
          aria-label={`Issue ${number}`}
        >
          {number}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <h3 className="font-semibold">{issue.type}</h3>
            <span className={`text-sm font-medium sev-text-${issue.severity}`}>
              {SEVERITY_LABEL[issue.severity]}
            </span>
          </div>
          <p className="mt-1 text-sm leading-relaxed">{issue.why}</p>
          {inImage && (
            <p className="mt-2 rounded-md bg-desk/70 px-3 py-2 text-sm">
              <span className="text-muted">In the image: </span>
              {issue.excerpt}
            </p>
          )}
          <p className="mt-2 text-xs text-muted">
            Source{" "}
            <span className="rounded bg-desk px-1.5 py-0.5 font-semibold text-ink">{issue.source_code}</span>
            {issue.engine === "rules"
              ? " · brand rule"
              : issue.engine === "vision"
                ? " · image check"
                : ` · AI check, ${Math.round(issue.confidence * 100)}% sure`}
            {issue.needs_human && <> · a reviewer must confirm this</>}
          </p>

          {issue.fix !== null && mode === "idle" && (
            <p className="mt-3 rounded-md bg-desk/70 px-3 py-2 font-serif text-[1.05rem]">
              <del className="text-muted">{issue.excerpt}</del>
              <span className="mx-2 text-muted" aria-hidden>
                →
              </span>
              <span className="sr-only">replace with</span>
              <ins className="no-underline font-medium">{issue.fix === "" ? "(remove)" : issue.fix}</ins>
            </p>
          )}

          {!locked && mode === "idle" && inImage && (
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" disabled={busy} className="btn btn-primary" onClick={() => onDecide({ decision: "edited" })}>
                Mark as fixed in the design
              </button>
              <button type="button" disabled={busy} className="btn btn-ghost" onClick={() => setMode("ignore")}>
                Ignore
              </button>
            </div>
          )}

          {!locked && mode === "idle" && !inImage && (
            <div className="mt-3 flex flex-wrap gap-2">
              {issue.fix !== null && (
                <button type="button" disabled={busy} className="btn btn-primary" onClick={() => onDecide({ decision: "accepted" })}>
                  Accept fix
                </button>
              )}
              <button type="button" disabled={busy} className="btn btn-ghost" onClick={() => setMode("edit")}>
                Edit
              </button>
              <button type="button" disabled={busy} className="btn btn-ghost" onClick={() => setMode("ignore")}>
                Ignore
              </button>
            </div>
          )}

          {mode === "edit" && (
            <form
              className="mt-3 space-y-2"
              onSubmit={(e) => {
                e.preventDefault();
                onDecide({ decision: "edited", edited_text: text });
              }}
            >
              <label className="block text-xs text-muted" htmlFor={`edit-${issue.id}`}>
                Replace “{issue.excerpt}” with
              </label>
              <input id={`edit-${issue.id}`} className="field font-serif" value={text} onChange={(e) => setText(e.target.value)} autoFocus />
              <div className="flex gap-2">
                <button className="btn btn-primary" disabled={busy}>Save edit</button>
                <button type="button" className="btn btn-ghost" onClick={() => setMode("idle")}>Cancel</button>
              </div>
            </form>
          )}

          {mode === "ignore" && (
            <form
              className="mt-3 space-y-2"
              onSubmit={(e) => {
                e.preventDefault();
                onDecide({ decision: "ignored", reason });
              }}
            >
              <label className="block text-xs text-muted" htmlFor={`why-${issue.id}`}>
                Why is this fine? Your reason helps the brand team improve unclear rules.
              </label>
              <input
                id={`why-${issue.id}`}
                className="field"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Quoting a customer review"
                autoFocus
              />
              <div className="flex gap-2">
                <button className="btn btn-primary" disabled={busy || reason.trim().length < 3}>Ignore issue</button>
                <button type="button" className="btn btn-ghost" onClick={() => setMode("idle")}>Cancel</button>
              </div>
            </form>
          )}
        </div>
      </div>
    </li>
  );
});
