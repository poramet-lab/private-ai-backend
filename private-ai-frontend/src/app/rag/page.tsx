'use client';

import { useState } from 'react';

type Hit = {
  id: string | number;
  score: number;
  path?: string | null;
  preview?: string | null;
  project_id?: string | null;
  room_id?: string | null;
  file?: string | null;
  file_path?: string | null;
  created_at?: number | null;
};

export default function RagPage() {
  const [query, setQuery] = useState('สรุปภาพรวมโปรเจกต์');
  const [limit, setLimit] = useState(5);
  const [loading, setLoading] = useState(false);
  const [hits, setHits] = useState<Hit[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const onSearch = async () => {
    setLoading(true);
    setErr(null);
    setHits([]);
    try {
      const r = await fetch('/api/rag-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-store',
        body: JSON.stringify({
          query,
          project_id: 'demo',
          room_id: 'general',
          limit,
          score_threshold: 0.30,
        }),
      });
      const data = await r.json();
      if (!r.ok) {
        setErr(data?.detail || JSON.stringify(data));
      } else {
        setHits(data?.hits || []);
      }
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <h1 className="text-2xl font-semibold">RAG Search (frontend → backend)</h1>

      <div className="space-y-3">
        <label className="block text-sm font-medium">คำค้น</label>
        <input
          className="w-full border rounded px-3 py-2"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="พิมพ์คำค้น เช่น สรุปภาพรวมโปรเจกต์"
        />
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium">Limit</label>
          <input
            type="number"
            className="w-24 border rounded px-2 py-1"
            value={limit}
            min={1}
            max={20}
            onChange={(e) => setLimit(parseInt(e.target.value || '1', 10))}
          />
          <button
            onClick={onSearch}
            disabled={loading}
            className="ml-auto bg-black text-white rounded px-4 py-2 disabled:opacity-60"
          >
            {loading ? 'กำลังค้นหา…' : 'ค้นหา'}
          </button>
        </div>
      </div>

      {err && (
        <div className="border border-red-300 bg-red-50 text-red-700 rounded p-3 text-sm">
          Error: {err}
        </div>
      )}

      <div className="space-y-4">
        {hits.length > 0 && (
          <div className="text-sm text-gray-600">พบผลลัพธ์ {hits.length} รายการ</div>
        )}
        {hits.map((h, i) => (
          <div key={`${h.id}-${i}`} className="border rounded p-4 space-y-1">
            <div className="text-sm text-gray-500">score: {h.score.toFixed(3)}</div>
            {h.path && <div className="font-medium">{h.path}</div>}
            {h.preview && (
              <pre className="text-sm whitespace-pre-wrap text-gray-800">
                {h.preview}
              </pre>
            )}
          </div>
        ))}
        {!loading && !err && hits.length === 0 && (
          <div className="text-sm text-gray-500">ยังไม่มีผลลัพธ์</div>
        )}
      </div>
    </div>
  );
}
