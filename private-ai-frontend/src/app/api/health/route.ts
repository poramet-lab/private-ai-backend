export async function GET() {
  const base = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8081";
  const r = await fetch(`${base}/health`, { cache: "no-store" });
  const data = await r.json();
  return new Response(JSON.stringify(data), {
    status: r.status,
    headers: { "Content-Type": "application/json" },
  });
}
