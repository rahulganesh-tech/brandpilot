"use client";

import type { Issue, Severity } from "@/lib/types";

const RANK: Record<Severity, number> = { low: 0, medium: 1, high: 2 };

interface Props {
  content: string;
  issues: Issue[];
  numbers: Map<string, number>;
  activeId: string | null;
  onSelect: (id: string) => void;
}

/** The draft set as a proof, with each open issue underlined and numbered. */
export function Proof({ content, issues, numbers, activeId, onSelect }: Props) {
  const marked = issues.filter(
    (i) => i.span_start >= 0 && i.span_end <= content.length && i.span_end > i.span_start,
  );
  const cuts = new Set<number>([0, content.length]);
  for (const i of marked) {
    cuts.add(i.span_start);
    cuts.add(i.span_end);
  }
  const points = [...cuts].sort((a, b) => a - b);

  const parts: React.ReactNode[] = [];
  for (let k = 0; k < points.length - 1; k++) {
    const a = points[k];
    const b = points[k + 1];
    const text = content.slice(a, b);
    const covering = marked.filter((i) => i.span_start <= a && i.span_end >= b);
    if (covering.length === 0) {
      parts.push(text);
    } else {
      const top = covering.reduce((x, y) => (RANK[y.severity] > RANK[x.severity] ? y : x));
      const active = covering.some((i) => i.id === activeId);
      const target = covering.find((i) => i.id === activeId) ?? top;
      parts.push(
        <mark
          key={`m${a}`}
          className={`sev-${top.severity}${active ? " is-active" : ""}`}
          onClick={() => onSelect(target.id)}
          title={covering.map((i) => i.type).join(", ")}
        >
          {text}
        </mark>,
      );
    }
    const ending = marked.filter((x) => x.span_end === b);
    if (ending.length > 0) {
      parts.push(
        <sup key={`n${b}`}>
          {ending.map((i, k) => (
            <span key={i.id} className={`sev-text-${i.severity}`}>
              {k > 0 && ","}
              {numbers.get(i.id)}
            </span>
          ))}
        </sup>,
      );
    }
  }

  return <div className="proof">{parts}</div>;
}
