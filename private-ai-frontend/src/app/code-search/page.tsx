"use client";

import React, { useState } from "react";

/* ---------- Types ---------- */
type CodeHit = {
  id: string;
  score: number;
  path: string;
  start: number;
  end: number;
  commit: string;
  preview: string | null;
};

type Snippet = {
  start: number;
  end: number;
  text: string;
};

type SnippetMap = Record<string, Snippet | undefined>;

/* ---------- Page ---------- */
export default function CodeSearchPage() {
  const [query, setQuery] = useState("ingest upload endpoint");
  const [limit, setLimit] = useState(5);
  const [hits, setHits] = useState<CodeHit[] | null>(null);
  const [snippets, setSnippets] = useState<SnippetMap>({});
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  /* ----- call Next.js API -> backend /code/search ----- */
  async function doSearch(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    setHits(null);
    setSnippets({});

    try {
      const r = await fetch(`/api/code-search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ query, limit }),
      });

      if (!r.ok) {
        const msg = await safeText(r);
        throw new Error(`HTTP ${r.status}${msg ? `: ${msg}` : ""}`);
      }
      const data = (await r.json()) as { hits: CodeHit[] };
      setHits(data.hits ?? []);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  /* ----- fetch snippet from /api/code-snippet ----- */
  async function fetchSnippet(h: CodeHit, opt?: { expand?: number }) {
    try {
      const body: any = {
        path: h.path,
        start: h.start,
        end: h.end,
      };
      if (opt?.expand) body.expand = opt.expand;

      const r = await fetch(`/api/code-snippet`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const msg = await safeText(r);
        throw new Error(`snippet HTTP ${r.status}${msg ? `: ${msg}` : ""}`);
      }
      const data = (await r.json()) as {
        file_path: string;
        start: number;
        end: number;
        snippet: string;
      };

      setSnippets((prev) => ({
        ...prev,
        [h.id]: { start: data.start, end: data.end, text: data.snippet },
      }));
    } catch (e: any) {
      alert(e?.message || String(e));
    }
  }

  async function copySnippet(id: string) {
    const s = snippets[id];
    if (!s?.text) return;
    try {
      await navigator.clipboard.writeText(s.text);
      alert("คัดลอกแล้ว");
    } catch {
      // fallback
      const ta = document.createElement("textarea");
      ta.value = s.text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      alert("คัดลอกแล้ว");
    }
  }

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-semibold">Code Search</h1>

      {/* form */}
      <form onSubmit={doSearch} className="flex items-center gap-3">
        <input
          className="flex-1 border rounded px-3 py-2"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="พิมพ์คำค้น…"
        />
        <input
          type="number"
          min={1}
          max={20}
          className="w-20 border rounded px-2 py-2"
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value || 5))}
          title="limit"
        />
        <button
          type="submit"
          className="px-4 py-2 rounded bg-black text-white hover:opacity-90"
          disabled={loading}
        >
          {loading ? "ค้นหา…" : "ค้นหา"}
        </button>
      </form>

      {/* error */}
      {err && <div className="text-red-600">Error: {err}</div>}

      {/* results */}
      {hits?.length ? (
        <div className="space-y-4">
          {hits.map((h) => (
            <div key={h.id} className="rounded border p-4">
              <div className="text-xs text-gray-600 flex flex-wrap gap-x-4 gap-y-1">
                <span>score: {h.score.toFixed(3)}</span>
                <span>
                  {h.path} [{h.start}–{h.end}]
                </span>
                <span>commit: {h.commit}</span>
              </div>

              {/* actions */}
              <div className="flex items-center gap-3 text-sm text-blue-700 mt-3">
                <button
                  className="px-2 py-1 rounded bg-blue-50 hover:bg-blue-100"
                  onClick={() => fetchSnippet(h)}
                  title="ดูโค้ดช่วงนี้"
                >
                  👁️ ดูโค้ด
                </button>

                <button
                  className="px-2 py-1 rounded bg-blue-50 hover:bg-blue-100 disabled:opacity-50"
                  disabled={!snippets[h.id]?.text}
                  onClick={() => copySnippet(h.id)}
                  title="คัดลอกเนื้อหา"
                >
                  📋 คัดลอก
                </button>

                <button
                  className="px-2 py-1 rounded bg-blue-50 hover:bg-blue-100"
                  onClick={() => fetchSnippet(h, { expand: 200 })}
                  title="ขยายช่วงรอบๆ ±200 ตัวอักษร"
                >
                  ➕ ขยาย ±200
                </button>

                {/* FIX: Use a frontend API route as a proxy for downloading */}
                <a
                  className="px-2 py-1 rounded bg-blue-50 hover:bg-blue-100"
                  href={`/api/download-raw?path=${encodeURIComponent(h.path)}`}
                  title="ดาวน์โหลดช่วงนี้เป็นไฟล์ .txt"
                >
                  💾 ดาวน์โหลด
                </a>
              </div>

              {/* snippet */}
              {snippets[h.id]?.text ? (
                <>
                  <div className="mt-3 text-xs opacity-70">
                    slice: {snippets[h.id]!.start}–{snippets[h.id]!.end}
                  </div>
                  <pre className="mt-1 bg-gray-900 text-gray-100 text-sm p-3 rounded overflow-x-auto">
                    <code>{snippets[h.id]!.text}</code>
                  </pre>
                </>
              ) : (
                <div className="mt-3 text-xs text-gray-500">
                  กด “ดูโค้ด” เพื่อโหลดช่วงนี้
                </div>
              )}
            </div>
          ))}
        </div>
      ) : hits && !hits.length ? (
        <div className="text-sm text-gray-500">ไม่พบผลลัพธ์</div>
      ) : null}
    </div>
  );
}

/* ---------- utils ---------- */
async function safeText(r: Response): Promise<string> {
  try {
    return await r.text();
  } catch {
    return "";
  }
}
