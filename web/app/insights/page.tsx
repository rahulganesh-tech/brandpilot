"use client";

import { useEffect, useState } from "react";
import { useWorkspace } from "@/components/Workspace";
import { api, STATUS_LABEL } from "@/lib/api";
import type { Brand, Insights, ScanStatus } from "@/lib/types";

export default function InsightsPage() {
  const { brand: current } = useWorkspace();
  const [data, setData] = useState<Insights | null>(null);
  const [brand, setBrand] = useState<Brand | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!current) return;
    Promise.all([api<Insights>(`/brands/${current.id}/insights`), api<Brand>(`/brands/${current.id}`)])
      .then(([i, b]) => {
        setData(i);
        setBrand(b);
      })
      .catch((e: Error) => setError(e.message));
  }, [current]);

  if (!data || !brand) return <p className="text-muted">{error ?? "Loading…"}</p>;
  const ruleText = new Map(brand.rules.map((r) => [r.code, r.message]));
  const statuses: ScanStatus[] = ["draft", "in_review", "sent_back", "approved"];
  const totalFlags = data.rules.reduce((n, r) => n + r.total, 0);

  return (
    <div>
      <h1 className="font-serif text-4xl tracking-tight">Insights</h1>
      <p className="mt-2 text-muted">Where content goes wrong, and which guidelines people find unclear.</p>

      <dl className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-rule bg-rule sm:grid-cols-5">
        {statuses.map((s) => (
          <div key={s} className="bg-paper px-5 py-4">
            <dt className="text-sm text-muted">{STATUS_LABEL[s]}</dt>
            <dd className="font-serif text-3xl">{data.scans_by_status[s] ?? 0}</dd>
          </div>
        ))}
        <div className="bg-paper px-5 py-4">
          <dt className="text-sm text-muted">Flags raised</dt>
          <dd className="font-serif text-3xl">{totalFlags}</dd>
        </div>
      </dl>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">Guideline Gap Radar</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Rules that creators ignore at least half the time. A rule that keeps getting overridden is usually unclear
          or out of date, so it’s worth rewording.
        </p>
        {data.gap_radar.length === 0 ? (
          <p className="mt-4 rounded-lg border border-rule bg-paper px-5 py-4 text-sm">
            No unclear rules yet. Rules show up here once they’ve been flagged twice and ignored at least half the time.
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {data.gap_radar.map((r) => (
              <li key={r.source_code} className="rounded-xl border border-medium/40 bg-paper p-5">
                <div className="flex flex-wrap items-baseline gap-x-3">
                  <span className="font-semibold">{r.source_code}</span>
                  <span className="text-sm text-muted">{r.type}</span>
                  <span className="ml-auto text-sm font-semibold text-medium">
                    Ignored {r.ignored} of {r.total} times
                  </span>
                </div>
                <p className="mt-1">{ruleText.get(r.source_code) ?? "Rule no longer exists."}</p>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-desk" aria-hidden>
                  <div className="h-full bg-medium" style={{ width: `${Math.round(r.override_rate * 100)}%` }} />
                </div>
                {r.sample_reasons && r.sample_reasons.length > 0 && (
                  <div className="mt-3 text-sm">
                    <p className="text-muted">What creators said:</p>
                    <ul className="mt-1 list-disc pl-5">
                      {r.sample_reasons.map((s, k) => <li key={k}>“{s}”</li>)}
                    </ul>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">Every rule that has fired</h2>
        {data.rules.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No flags yet. Check a draft to see results here.</p>
        ) : (
          <div className="mt-3 overflow-x-auto rounded-xl border border-rule bg-paper">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="text-muted">
                <tr className="border-b border-rule">
                  <th className="px-4 py-2 font-medium">Rule</th>
                  <th className="px-4 py-2 font-medium">Type</th>
                  <th className="px-4 py-2 text-right font-medium">Flagged</th>
                  <th className="px-4 py-2 text-right font-medium">Fixed</th>
                  <th className="px-4 py-2 text-right font-medium">Ignored</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {data.rules.map((r) => (
                  <tr key={r.source_code}>
                    <td className="px-4 py-2 font-semibold">{r.source_code}</td>
                    <td className="px-4 py-2">{r.type}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{r.total}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{r.fixed}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{r.ignored}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
