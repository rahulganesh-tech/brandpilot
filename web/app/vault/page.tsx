"use client";

import { useCallback, useEffect, useState } from "react";
import { useWorkspace } from "@/components/Workspace";
import { api, send, SEVERITY_LABEL } from "@/lib/api";
import type { Brand, RuleKind, Severity } from "@/lib/types";

const KIND_LABEL: Record<RuleKind, string> = {
  banned_word: "Banned word",
  term: "Correct term",
  tone: "Tone pattern",
  claim_policy: "Claim policy",
  accessibility: "Accessibility",
};

const EMPTY_RULE = { code: "", kind: "banned_word" as RuleKind, pattern: "", replacement: "", message: "", severity: "medium" as Severity };

export default function VaultPage() {
  const { brand: current, role } = useWorkspace();
  const [brand, setBrand] = useState<Brand | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [guide, setGuide] = useState("");
  const [fact, setFact] = useState({ code: "", statement: "", source: "" });
  const [rule, setRule] = useState(EMPTY_RULE);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!current) return;
    try {
      const b = await api<Brand>(`/brands/${current.id}`);
      setBrand(b);
      setGuide(b.voice_guide);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [current]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(fn: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await fn();
      await load();
      setNotice(done);
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (!brand) {
    return (
      <div className="max-w-xl">
        <h1 className="font-serif text-3xl">Brand vault</h1>
        <p className="mt-2 text-muted">{error ?? "Loading brand vault…"}</p>
      </div>
    );
  }
  const canEdit = role === "manager";

  return (
    <div>
      <h1 className="font-serif text-4xl tracking-tight">{brand.name} brand vault</h1>
      <p className="mt-2 max-w-2xl text-muted">
        The single source of truth. Every flag BrandPilot raises points back to a rule or an approved fact here.
        {!canEdit && " Switch “Viewing as” to Manager to make changes."}
      </p>
      <div aria-live="polite" className="mt-3 min-h-6 text-sm">
        {error && <span role="alert" className="text-high">{error}</span>}
        {notice && <span className="text-ok">{notice}</span>}
      </div>

      <section className="mt-6 rounded-xl border border-rule bg-paper p-6">
        <h2 className="text-lg font-semibold">Voice guide</h2>
        <p className="text-sm text-muted">How the brand sounds. The AI tone check quotes from this.</p>
        <textarea
          aria-label="Voice guide"
          className="field mt-3 font-serif text-[1.05rem] leading-relaxed"
          rows={10}
          value={guide}
          readOnly={!canEdit}
          onChange={(e) => setGuide(e.target.value)}
        />
        {canEdit && (
          <button
            type="button"
            className="btn btn-primary mt-3"
            disabled={busy || guide === brand.voice_guide}
            onClick={() => act(() => send(`/brands/${brand.id}`, "PATCH", { voice_guide: guide }), "Voice guide saved.")}
          >
            Save voice guide
          </button>
        )}
      </section>

      <section className="mt-6 rounded-xl border border-rule bg-paper p-6">
        <h2 className="text-lg font-semibold">Approved facts ({brand.facts.length})</h2>
        <p className="text-sm text-muted">Claims in a draft must match one of these, or they get flagged.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="text-muted">
              <tr>
                <th className="py-2 pr-3 font-medium">Code</th>
                <th className="py-2 pr-3 font-medium">Fact</th>
                <th className="py-2 pr-3 font-medium">Source</th>
                {canEdit && <th className="py-2"><span className="sr-only">Actions</span></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {brand.facts.map((f) => (
                <tr key={f.id}>
                  <td className="py-2 pr-3 font-semibold whitespace-nowrap">{f.code}</td>
                  <td className="py-2 pr-3">{f.statement}</td>
                  <td className="py-2 pr-3 text-muted">{f.source}</td>
                  {canEdit && (
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        disabled={busy}
                        className="text-sm text-high hover:underline"
                        onClick={() => act(() => send(`/facts/${f.id}`, "DELETE"), `Deleted ${f.code}.`)}
                      >
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {canEdit && (
          <form
            className="mt-4 grid gap-2 sm:grid-cols-[110px_1fr_200px_auto]"
            onSubmit={async (e) => {
              e.preventDefault();
              const ok = await act(() => send(`/brands/${brand.id}/facts`, "POST", [fact]), `Saved ${fact.code}.`);
              if (ok) setFact({ code: "", statement: "", source: "" });
            }}
          >
            <input className="field" placeholder="F-16" aria-label="Fact code" value={fact.code} onChange={(e) => setFact({ ...fact, code: e.target.value })} required />
            <input className="field" placeholder="The approved statement" aria-label="Fact" value={fact.statement} onChange={(e) => setFact({ ...fact, statement: e.target.value })} required />
            <input className="field" placeholder="Where it comes from" aria-label="Source" value={fact.source} onChange={(e) => setFact({ ...fact, source: e.target.value })} />
            <button className="btn btn-primary" disabled={busy}>Add fact</button>
          </form>
        )}
      </section>

      <section className="mt-6 rounded-xl border border-rule bg-paper p-6">
        <h2 className="text-lg font-semibold">Rules ({brand.rules.length})</h2>
        <p className="text-sm text-muted">Exact checks that run first on every draft.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-muted">
              <tr>
                <th className="py-2 pr-3 font-medium">Code</th>
                <th className="py-2 pr-3 font-medium">Type</th>
                <th className="py-2 pr-3 font-medium">Looks for</th>
                <th className="py-2 pr-3 font-medium">Suggests</th>
                <th className="py-2 pr-3 font-medium">Message</th>
                <th className="py-2 pr-3 font-medium">Risk</th>
                {canEdit && <th className="py-2"><span className="sr-only">Actions</span></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {brand.rules.map((r) => (
                <tr key={r.id} className="align-top">
                  <td className="py-2 pr-3 font-semibold whitespace-nowrap">{r.code}</td>
                  <td className="py-2 pr-3 whitespace-nowrap">{KIND_LABEL[r.kind]}</td>
                  <td className="py-2 pr-3"><code className="break-all text-xs">{r.pattern}</code></td>
                  <td className="py-2 pr-3">{r.replacement ?? <span className="text-muted">Human edit</span>}</td>
                  <td className="py-2 pr-3">{r.message}</td>
                  <td className={`py-2 pr-3 whitespace-nowrap sev-text-${r.severity}`}>{SEVERITY_LABEL[r.severity]}</td>
                  {canEdit && (
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        disabled={busy}
                        className="text-sm text-high hover:underline"
                        onClick={() => act(() => send(`/rules/${r.id}`, "DELETE"), `Deleted ${r.code}.`)}
                      >
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {canEdit && (
          <form
            className="mt-5 grid gap-2 sm:grid-cols-6"
            onSubmit={async (e) => {
              e.preventDefault();
              const body = [{ ...rule, replacement: rule.replacement === "" ? null : rule.replacement }];
              const ok = await act(() => send(`/brands/${brand.id}/rules`, "POST", body), `Saved ${rule.code}.`);
              if (ok) setRule(EMPTY_RULE);
            }}
          >
            <input className="field" placeholder="R-5.1" aria-label="Rule code" value={rule.code} onChange={(e) => setRule({ ...rule, code: e.target.value })} required />
            <select className="field" aria-label="Rule type" value={rule.kind} onChange={(e) => setRule({ ...rule, kind: e.target.value as RuleKind })}>
              {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input
              className="field"
              placeholder={rule.kind === "banned_word" || rule.kind === "term" ? "Word or phrase" : "Regex pattern"}
              aria-label="Looks for"
              value={rule.pattern}
              onChange={(e) => setRule({ ...rule, pattern: e.target.value })}
              required
            />
            <input className="field" placeholder="Suggested fix (optional)" aria-label="Suggested fix" value={rule.replacement} onChange={(e) => setRule({ ...rule, replacement: e.target.value })} />
            <select className="field" aria-label="Risk" value={rule.severity} onChange={(e) => setRule({ ...rule, severity: e.target.value as Severity })}>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High risk</option>
            </select>
            <button className="btn btn-primary" disabled={busy}>Add rule</button>
            <input
              className="field sm:col-span-6"
              placeholder="Message shown to the creator, with the guideline section"
              aria-label="Message"
              value={rule.message}
              onChange={(e) => setRule({ ...rule, message: e.target.value })}
              required
            />
          </form>
        )}
      </section>
    </div>
  );
}
