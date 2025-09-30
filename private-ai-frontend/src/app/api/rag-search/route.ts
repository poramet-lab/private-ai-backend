// src/app/api/rag-search/route.ts
import { NextRequest } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const { query, limit = 5 } = await req.json();

    const base = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8081";
    const r = await fetch(`${base}/rag/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // ส่ง project_id / room_id ชัดเจน ตรงกับที่คุณ ingest: demo / general
      body: JSON.stringify({
        query,
        limit,
        project_id: "demo",
        room_id: "general",
        score_threshold: 0.30,
      }),
    });

    const data = await r.json();
    return new Response(JSON.stringify(data), {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err: any) {
    return new Response(
      JSON.stringify({ detail: String(err?.message || err) }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}
