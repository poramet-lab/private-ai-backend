"use client";

import { useState } from "react";

type CodeHit = {
  id: string;
  score: number;
  path: string;
  start: number;
  end: number;
  commit: string;
  preview: string | null;
};

type CodeAnswerResp = {
  answer: string;
  sources: CodeHit[];
};

export default function CodeAnswerPage() {
  const [query, setQuery] = useState("สรุป endpoint สำหรับ ingest และ rag ในโปรเจกต์นี้");
  const [limit, setLimit] = useState(5);
  const [provider, setProvider] = useState<"chatgpt" | "local">("chatgpt");
  const [model, setModel] = useState<string>(""); // เว้นว่างได้
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [resp, setResp] = useState<CodeAnswerResp | null>(null);

  // เก็บสไนเป็ตที่กด “ดูโค้ด”
  const [snippets, setSnippets] = useState<Record<string, { text: string }>>({});

  async function onAsk(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    setResp(null);

    try {
      const body: any = { query, limit, provider };
      if (model.trim()) body.model = model.trim();

      const r = await fetch("/api/code-answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify(body),
      });

      if (!r.ok) {
        const text = await r.text();
        throw new Error(`HTTP ${r.status}: ${text}`);
      }

      const data = (await r.json()) as CodeAnswerResp;
      setResp(data);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadSnippet(hit: CodeHit) {
    const key = hit.id;
    if (snippets[key]) return; // เคยโหลดแล้ว

    try {
      const r = await fetch("/api/code-snippet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify({ path: hit.path, start: hit.start, end: hit.end }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setSnippets((s) => ({ ...s, [key]: { text: data.snippet || "" } }));
    } catch (e) {
      setSnippets((s) => ({ ...s, [key]: { text: `โหลดสไนเป็ตไม่สำเร็จ: ${String(e)}` } }));
    }
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-semibold">Code Answer</h1>

      <form onSubmit={onAsk} className="space-y-3">
        <textarea
          className="w-full border rounded p-3 bg-white/90 text-gray-900"
          rows={3}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="พิมพ์คำถามเกี่ยวกับโค้ด..."
        />
        <div className="flex gap-3 items-center">
          <label className="text-sm">Limit</label>
          <input
            type="number"
            min={1}
            max={10}
            value={limit}
            onChange={(e) => setLimit(parseInt(e.target.value || "5", 10))}
            className="w-20 border rounded p-2"
          />

          <label className="text-sm ml-4">Provider</label>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value as "chatgpt" | "local")}
            className="border rounded p-2"
          >
            <option value="chatgpt">chatgpt</option>
            <option value="local">local</option>
          </select>

          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="model (เว้นว่างได้)"
            className="flex-1 border rounded p-2"
          />

          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
          >
            {loading ? "กำลังถาม..." : "ถาม"}
          </button>
        </div>
      </form>

      {err && <div className="text-red-600">Error: {err}</div>}

      {resp && (
        <div className="space-y-6">
          <section>
            <h2 className="text-lg font-medium mb-2">คำตอบ</h2>
            <pre className="bg-gray-900 text-gray-100 text-sm p-4 rounded whitespace-pre-wrap">
              {resp.answer || "(ว่าง)"}
            </pre>
          </section>

          <section>
            <h2 className="text-lg font-medium mb-2">แหล่งที่มา</h2>
            <div className="space-y-4">
              {resp.sources.map((h) => (
                <div key={h.id} className="border rounded p-3 bg-white/90 text-gray-900">
                  <div className="text-sm">
                    <span className="font-semibold">score:</span>{" "}
                    {h.score.toFixed(3)} • <span className="font-semibold">{h.path}</span>{" "}
                    [{h.start}–{h.end}]
                  </div>
                  <div className="text-xs text-gray-600 break-all">
                    commit: {h.commit}
                  </div>

                  <div className="mt-2 flex gap-2">
                    <button
                      onClick={() => loadSnippet(h)}
                      className="px-3 py-1 text-sm rounded border"
                    >
                      ดูโค้ด
                    </button>
                    <a
                      href={`/api/code-snippet`}
                      onClick={(e) => {
                        // ส่งดาวน์โหลดเป็นไฟล์ .txt ด้วย POST programmatic
                        e.preventDefault();
                        const form = document.createElement("form");
                        form.method = "POST";
                        form.action = "/api/code-snippet";
                        form.style.display = "none";
                        const payload = {
                          path: h.path,
                          start: h.start,
                          end: h.end,
                          download: true,
                        };
                        const input = document.createElement("input");
                        input.type = "hidden";
                        input.name = "payload";
                        input.value = JSON.stringify(payload);
                        form.appendChild(input);
                        document.body.appendChild(form);
                        form.submit();
                        setTimeout(() => form.remove(), 1000);
                      }}
                      className="px-3 py-1 text-sm rounded border"
                    >
                      ดาวน์โหลด
                    </a>
                  </div>

                  {snippets[h.id]?.text ? (
                    <pre className="mt-3 bg-gray-900 text-gray-100 text-sm p-3 rounded overflow-x-auto">
                      {snippets[h.id].text}
                    </pre>
                  ) : h.preview ? (
                    <pre className="mt-3 bg-gray-100 text-gray-800 text-sm p-3 rounded overflow-x-auto">
                      {(h.preview || "").slice(0, 800)}
                    </pre>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
