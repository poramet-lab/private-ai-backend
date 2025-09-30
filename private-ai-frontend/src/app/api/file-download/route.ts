import { NextRequest } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const filePath: string | undefined = body?.file_path;

    if (!filePath || typeof filePath !== "string") {
      return new Response(JSON.stringify({ detail: "Invalid body. Expect { file_path }" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // อ่านไฟล์จากดิสก์ (จำกัดขนาดเพื่อความปลอดภัย เช่น 5MB)
    const MAX = 5 * 1024 * 1024;
    const stat = await fs.stat(filePath);
    if (stat.size > MAX) {
      return new Response(JSON.stringify({ detail: `File too large (${stat.size} bytes) > 5MB` }), {
        status: 413,
        headers: { "Content-Type": "application/json" },
      });
    }

    const buf = await fs.readFile(filePath);
    const filename = path.basename(filePath);

    return new Response(buf, {
      status: 200,
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Length": String(buf.length),
        "Content-Disposition": `attachment; filename="${encodeURIComponent(filename)}"`,
      },
    });
  } catch (err: any) {
    return new Response(JSON.stringify({ detail: String(err?.message || err) }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}
