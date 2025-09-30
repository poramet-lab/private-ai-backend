"use client";

import { useState } from "react";

type Hit = {
  id: number;
  score: number;
  room_id: string | null;
  project_id: string | null;
  file: string | null;
  file_path: string | null;
  preview: string | null;
  created_at: number | null;
};

export default function RagSearchPage() {
  const [query, setQuery] = useState("สรุปภาพรวมโปรเจกต์");
  const [limit, setLimit] = useState(5);
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [previews, setPreviews] = useState<Record<number, string>>({});
  const [downloading, setDownloading] = useState<number | null>(null);

  async function doSearch(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    setHits(null);
    setPreviews({});
    try {
      const r = await fetch("/api/rag-search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ query, limit }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = (await r.json()) as { hits: Hit[] };
      setHits(data.hits || []);
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }

  async function showPreview(h: Hit) {
    if (!h.file_path) return;
    try {
      const r = await fetch("/api/file-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ file_path: h.file_path, max_bytes: 1200 }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setPreviews((old) => ({ ...old, [h.id]: data.preview || "" }));
    } catch (e: any) {
      setPreviews((old) => ({ ...old, [h.id]: `โหลดพรีวิวไม่สำเร็จ: ${String(e?.message || e)}` }));
    }
  }

  async function downloadFile(h: Hit) {
    if (!h.file_path) return;
    setDownloading(h.id);
    try {
      const r = await fetch("/api/file-download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ file_path: h.file_path }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = h.file || "download.bin";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert(`ดาวน์โหลดไม่สำเร็จ: ${String(e?.message || e)}`);
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div className="max-w-3xl mx-auto p-4 space-y-4">
      <h1 className="text-2xl font-semibold">RAG Search</h1>

      <form onSubmit={doSearch} className="flex items-center gap-2">
        <input
          className="flex-1 border rounded px-3 py-2"
          placeholder="พิมพ์คำค้น…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <input
          className="w-24 border rounded px-3 py-2"
          type="number"
          min={1}
          max={20}
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          title="จำนวนผลลัพธ์"
        />
        <button
          className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
          disabled={loading}
          type="submit"
        >
          {loading ? "กำลังค้นหา…" : "ค้นหา"}
        </button>
      </form>

      {err && (
        <div className="p-3 rounded bg-red-50 text-red-700 border border-red-200">
          Error: {err}
        </div>
      )}

      {hits && hits.length === 0 && <div>ไม่พบข้อมูล</div>}

      {hits && hits.length > 0 && (
        <ul className="space-y-3">
          {hits.map((h) => (
            <li key={h.id} className="border rounded p-3">
              <div className="text-sm text-gray-500">
                score: {h.score.toFixed(3)} • {h.file || "(no name)"}
              </div>
              <div className="text-xs text-gray-500 break-all">
                path: {h.file_path || "(unknown)"} <br />
                {h.created_at ? `created_at: ${h.created_at}` : null}
              </div>

              <div className="mt-2 flex gap-2">
                <button
                  className="px-3 py-1 rounded bg-gray-800 text-white"
                  onClick={() => showPreview(h)}
                >
                  ดูไฟล์
                </button>
                <button
                  className="px-3 py-1 rounded bg-blue-600 text-white disabled:opacity-50"
                  onClick={() => downloadFile(h)}
                  disabled={downloading === h.id}
                >
                  {downloading === h.id ? "กำลังดาวน์โหลด…" : "ดาวน์โหลด"}
                </button>
              </div>

              {previews[h.id] !== undefined && (
                <pre className="mt-3 bg-gray-900 text-gray-100 text-sm p-3 rounded overflow-x-auto">
{previews[h.id] || "(ว่าง)"}
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
