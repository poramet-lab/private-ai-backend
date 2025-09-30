import { NextRequest } from "next/server";
import fs from "node:fs/promises";

export async function POST(req: NextRequest) {
  try {
    const { file_path, max_bytes = 4000 } = await req.json();

    if (typeof file_path !== "string" || file_path.length === 0) {
      return new Response(JSON.stringify({ detail: "Invalid body. Expect { file_path }" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (typeof max_bytes !== "number" || max_bytes <= 0 || max_bytes > 20000) {
      return new Response(JSON.stringify({ detail: "Invalid max_bytes" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const fh = await fs.open(file_path, "r");
    try {
      const stat = await fh.stat();
      const toRead = Math.min(stat.size, max_bytes);
      const buf = Buffer.alloc(toRead);
      await fh.read(buf, 0, toRead, 0);
      const text = buf.toString("utf-8");

      return new Response(JSON.stringify({ file_path, size: stat.size, preview: text }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    } finally {
      await fh.close();
    }
  } catch (err: any) {
    return new Response(JSON.stringify({ detail: String(err?.message || err) }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}
