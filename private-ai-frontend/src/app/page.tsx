export default function Home() {
  return (
    <main className="min-h-screen px-6 py-10">
      <h1 className="text-2xl font-semibold">Private AI Frontend</h1>
      <p className="text-gray-600 mt-2">
        เลือกฟีเจอร์ที่ต้องการทดสอบ
      </p>

      <ul className="mt-6 space-y-3">
        <li>
          <a
            href="/code-search"
            className="inline-block px-4 py-2 rounded bg-black text-white hover:opacity-90"
          >
            Code Search
          </a>
        </li>
        <li>
          <a
            href="/rag-search"
            className="inline-block px-4 py-2 rounded bg-black text-white hover:opacity-90"
          >
            RAG Search
          </a>
        </li>
      </ul>
    </main>
  );
}
