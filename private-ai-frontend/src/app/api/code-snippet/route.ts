import { NextRequest } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";

export async function POST(req: NextRequest) {
  try {
    const { path: relPath, start, end } = await req.json();

    if (typeof relPath !== "string" || typeof start !== "number" || typeof end !== "number") {
      return new Response(JSON.stringify({ detail: "Invalid body. Expect { path, start, end }" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (start < 0 || end < start || end - start > 2000) {
      // กันยิงช่วงยาวเกินควร
      return new Response(JSON.stringify({ detail: "Invalid range" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // ระบุตำแหน่ง root ของ repo backend (ที่มีไฟล์ที่ถูกทำดัชนีไว้)
    // โครงสร้างของคุณคือ:
    //   ~/repos/work/private-ai-backend   <--- ROOT
    //   └─ private-ai-frontend            <--- แอป Next.js (เรากำลังรันอยู่ตรงนี้)
    const FRONT = process.cwd(); // ~/repos/work/private-ai-backend/private-ai-frontend
    const ROOT = path.resolve(FRONT, ".."); // ขึ้นไปหนึ่งระดับ -> ~/repos/work/private-ai-backend

    // ป้องกัน path traversal ด้วยการ normalize + ตรวจให้อยู่ใต้ ROOT
    const absPath = path.resolve(ROOT, relPath);
    if (!absPath.startsWith(ROOT + path.sep)) {
      return new Response(JSON.stringify({ detail: "Path not allowed" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const buf = await fs.readFile(absPath, "utf8");
    const slice = buf.slice(start, end);

    return new Response(
      JSON.stringify({ path: relPath, start, end, snippet: slice }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  } catch (err: any) {
    return new Response(JSON.stringify({ detail: String(err?.message || err) }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}
