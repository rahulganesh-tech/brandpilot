"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { useWorkspace } from "@/components/Workspace";
import { api, when } from "@/lib/api";
import type { ScanSummary } from "@/lib/types";

export default function ReviewPage() {
  const { brand, role } = useWorkspace();
  const [scans, setScans] = useState<ScanSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!brand) return;
    api<ScanSummary[]>(`/scans?brand_id=${brand.id}`).then(setScans).catch((e: Error) => setError(e.message));
  }, [brand]);

  const waiting = scans?.filter((s) => s.status === "in_review") ?? [];
  const done = scans?.filter((s) => s.status === "approved" || s.status === "sent_back") ?? [];

  return (
    <div className="max-w-3xl">
      <h1 className="font-serif text-4xl tracking-tight">Review queue</h1>
      <p className="mt-2 text-muted">
        Drafts the creators have cleaned up and sent for approval.
        {role === "creator" && " Switch “Viewing as” to Manager to approve or send back."}
      </p>
      {error && <p role="alert" className="mt-4 text-high">{error}</p>}

      <List title={`Waiting for review (${waiting.length})`} items={waiting} empty="Nothing is waiting. New submissions will show up here." loading={scans === null} />
      <List title="Recently decided" items={done.slice(0, 10)} empty="No decisions yet." loading={scans === null} />
    </div>
  );
}

function List({ title, items, empty, loading }: { title: string; items: ScanSummary[]; empty: string; loading: boolean }) {
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold text-muted">{title}</h2>
      {loading ? (
        <p className="mt-3 text-sm text-muted">Loading…</p>
      ) : items.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{empty}</p>
      ) : (
        <ul className="mt-3 divide-y divide-rule rounded-xl border border-rule bg-paper">
          {items.map((s) => (
            <li key={s.id}>
              <Link href={`/scans/${s.id}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-4 hover:bg-desk/60">
                <p className="min-w-0 flex-1 basis-64 truncate font-serif text-lg">{s.preview}</p>
                <StatusBadge status={s.status} />
                <span className="text-sm text-muted">
                  {s.open_issues > 0 ? `${s.open_issues} flagged for you` : "All flags resolved"}
                </span>
                <span className="text-sm text-muted">{s.author} · {when(s.updated_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
