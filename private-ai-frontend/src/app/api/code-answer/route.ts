export const dynamic = "force-dynamic";

import { NextRequest } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const base =
      process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8081";

    const body = await req.json(); // { query, limit?, provider?, model? }

    const r = await fetch(`${base}/code/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(body),
    });

    const text = await r.text();
    // ส่งสถานะ/เนื้อหากลับตามต้นทาง (ถ้าเป็น JSON ก็คืนเป็น JSON)
    try {
      const json = JSON.parse(text);
      return new Response(JSON.stringify(json), {
        status: r.status,
        headers: { "Content-Type": "application/json" },
      });
    } catch {
      return new Response(text, {
        status: r.status,
        headers: { "Content-Type": r.headers.get("content-type") || "text/plain" },
      });
    }
  } catch (e: any) {
    return new Response(
      JSON.stringify({ detail: e?.message || String(e) }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}