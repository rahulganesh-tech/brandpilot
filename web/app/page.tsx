"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { useWorkspace } from "@/components/Workspace";
import { CHANNELS, api, send, when } from "@/lib/api";
import type { ScanBundle, ScanSummary } from "@/lib/types";

const SAMPLE =
  "Meet India's #1 protein bar — 100% sugar-free! Grab yours now, guys!!";
const LIMIT = 20000;

export default function WritePage() {
  const router = useRouter();
  const { brand, brandError, person } = useWorkspace();
  const [mode, setMode] = useState<"text" | "image">("text");
  const [content, setContent] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [channel, setChannel] = useState("Instagram");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<ScanSummary[] | null>(null);

  useEffect(() => {
    if (!brand) return;
    api<ScanSummary[]>(`/scans?brand_id=${brand.id}`)
      .then(setDrafts)
      .catch(() => setDrafts([]));
  }, [brand]);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function checkImage(): Promise<ScanBundle> {
    const form = new FormData();
    form.append("brand_id", brand!.id);
    form.append("channel", channel.toLowerCase());
    form.append("author", person);
    form.append("file", file!);
    const res = await fetch("/api/scans/image", { method: "POST", body: form });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(typeof body.detail === "string" ? body.detail : `Upload failed (${res.status})`);
    }
    return res.json();
  }

  const ready = mode === "text" ? content.trim().length > 0 : file !== null;

  async function check() {
    if (!brand || !ready) return;
    setBusy(true);
    setError(null);
    try {
      const b =
        mode === "text"
          ? await send<ScanBundle>("/scans", "POST", {
              brand_id: brand.id,
              content,
              channel: channel.toLowerCase(),
              author: person,
            })
          : await checkImage();
      router.push(`/scans/${b.scan.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px]">
      <section>
        <h1 className="font-serif text-4xl leading-tight tracking-tight sm:text-5xl">
          Check it before the world sees it.
        </h1>
        <p className="mt-3 max-w-xl text-muted">
          Paste a post or upload a design. BrandPilot marks anything that breaks
          {brand ? ` ${brand.name}’s` : " your"} rules or approved facts, says why, and suggests a fix.
        </p>

        {brandError && (
          <p role="alert" className="mt-6 rounded-lg border border-high/40 bg-paper p-4 text-high">
            {brandError}
          </p>
        )}

        <div className="mt-8 rounded-xl border border-rule bg-paper shadow-[0_1px_0_#d9dce4,0_12px_32px_-18px_rgba(27,31,59,0.35)]">
          <div className="flex flex-wrap items-center gap-3 border-b border-rule px-5 py-3 text-sm">
            <div role="radiogroup" aria-label="What to check" className="flex rounded-md border border-rule p-0.5">
              {(["text", "image"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={mode === m}
                  onClick={() => setMode(m)}
                  className={`rounded px-3 py-1 ${mode === m ? "bg-ink text-white" : "text-muted hover:text-ink"}`}
                >
                  {m === "text" ? "Text" : "Image"}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-2">
              <span className="text-muted">Channel</span>
              <select
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
                className="rounded-md border border-rule bg-paper px-2 py-1"
              >
                {CHANNELS.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            {mode === "text" && (
              <button type="button" onClick={() => setContent(SAMPLE)} className="ml-auto text-accent hover:underline">
                Use a sample post
              </button>
            )}
          </div>
          {mode === "text" ? (
            <>
              <label htmlFor="draft" className="sr-only">
                Content to check
              </label>
              <textarea
                id="draft"
                value={content}
                onChange={(e) => setContent(e.target.value.slice(0, LIMIT))}
                placeholder="Write or paste your draft here…"
                rows={9}
                className="proof block w-full resize-y bg-transparent px-6 py-5 outline-none placeholder:text-muted/60"
              />
            </>
          ) : (
            <div className="px-6 py-6">
              <label
                htmlFor="design"
                className="flex min-h-56 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-rule px-4 py-6 text-center hover:border-muted"
              >
                {preview ? (
                  <img src={preview} alt="Selected design" className="max-h-72 w-auto rounded-md" />
                ) : (
                  <span className="font-serif text-xl">Choose a poster, ad or social graphic</span>
                )}
                <span className="text-sm text-muted">
                  {file ? `${file.name} · choose another` : "PNG, JPEG or WebP, up to 5 MB"}
                </span>
              </label>
              <input
                id="design"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="sr-only"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <p className="mt-3 text-sm text-muted">
                BrandPilot reads the text in the image and checks it, then checks text contrast and brand colours.
              </p>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3 border-t border-rule px-5 py-3">
            {mode === "text" && (
              <span className="text-sm text-muted">{content.length.toLocaleString("en-IN")} characters</span>
            )}
            {error && (
              <span role="alert" className="text-sm text-high">
                {error}
              </span>
            )}
            <button
              type="button"
              onClick={check}
              disabled={busy || !brand || !ready}
              className="btn btn-primary ml-auto"
            >
              {busy ? "Checking…" : mode === "text" ? "Check content" : "Check image"}
            </button>
          </div>
        </div>
      </section>

      <aside>
        <h2 className="text-sm font-semibold text-muted">Recent checks</h2>
        {drafts === null ? (
          <p className="mt-3 text-sm text-muted">Loading…</p>
        ) : drafts.length === 0 ? (
          <p className="mt-3 text-sm text-muted">Nothing checked yet. Your drafts will appear here.</p>
        ) : (
          <ul className="mt-3 divide-y divide-rule rounded-xl border border-rule bg-paper">
            {drafts.slice(0, 8).map((d) => (
              <li key={d.id}>
                <Link href={`/scans/${d.id}`} className="block px-4 py-3 hover:bg-desk/60">
                  <p className="line-clamp-2 font-serif text-[1.05rem] leading-snug">
                    {d.preview || (d.has_image ? "Image with no text" : "")}
                  </p>
                  <div className="mt-1.5 flex items-center gap-2 text-xs text-muted">
                    <StatusBadge status={d.status} />
                    <span className="capitalize">{d.channel}</span>
                    {d.has_image && <span>· image</span>}
                    <span className="ml-auto">
                      {d.open_issues > 0 ? `${d.open_issues} open` : "No open issues"}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted">{when(d.updated_at)}</p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
