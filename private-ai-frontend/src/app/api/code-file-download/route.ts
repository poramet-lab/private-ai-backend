import { NextRequest } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";

export async function POST(req: NextRequest) {
  try {
    const { rel_path } = await req.json();

    if (typeof rel_path !== "string" || !rel_path.trim()) {
      return new Response(JSON.stringify({ detail: "Invalid body. Expect { rel_path }" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    // โฟลเดอร์รากของซอร์สโค้ดฝั่ง backend ที่เรา index ไว้
    const repoRoot =
      process.env.REPO_ROOT || "/home/poramet/repos/work/private-ai-backend";

    const absPath = path.resolve(repoRoot, rel_path);

    // กัน path traversal: ต้องอยู่ใต้ repoRoot เท่านั้น
    const safeRoot = path.resolve(repoRoot) + path.sep;
    if (!absPath.startsWith(safeRoot)) {
      return new Response(JSON.stringify({ detail: "Path not allowed" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const buf = await fs.readFile(absPath);
    const filename = path.basename(absPath);

    return new Response(buf, {
      status: 200,
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": `attachment; filename="${filename}"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (err: any) {
    return new Response(
      JSON.stringify({ detail: String(err?.message || err) }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}
