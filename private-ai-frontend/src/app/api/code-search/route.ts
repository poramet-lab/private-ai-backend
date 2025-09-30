// src/app/api/code-search/route.ts
import { NextRequest } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const { query, limit = 5 } = await req.json();

    if (typeof query !== "string" || !query.trim()) {
      return new Response(JSON.stringify({ detail: "query is required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const base =
      process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8081";

    const upstream = await fetch(`${base}/code/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify({ query, limit }),
    });

    const text = await upstream.text();

    // ถ้า backend ตอบไม่ใช่ 2xx — ส่ง JSON อธิบาย error กลับไป
    if (!upstream.ok) {
      return new Response(
        JSON.stringify({
          detail: `Upstream ${upstream.status}`,
          base,
          path: "/code/search",
          body: text,
        }),
        { status: upstream.status, headers: { "Content-Type": "application/json" } }
      );
    }

    // ผ่านแล้ว: ส่งข้อความดิบ (ควรเป็น JSON จาก backend) กลับไปพร้อม content-type
    return new Response(text, {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err: any) {
    return new Response(
      JSON.stringify({ detail: err?.message || String(err) }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}
