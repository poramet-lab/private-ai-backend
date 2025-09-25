# === config / imports (put at very top) ===
import os, re, json, uuid, urllib.request, urllib.error, subprocess

# Qdrant / Ollama endpoints
QDRANT = "http://127.0.0.1:6333"
COLL   = "code_rag"

OLLAMA = "http://127.0.0.1:11435"   # ใช้ bge-m3 ฝั่ง embeddings

# ตำแหน่ง repo และ batch size
REPO  = os.path.abspath(os.getenv("CODE_REPO", os.path.expanduser("~/repos/work/private-ai-backend")))
BATCH = 16

# --- helpers ---
def sh(*args) -> str:
    """เรียกคำสั่ง shell แบบง่าย ๆ และคืนค่า stdout (strip)"""
    out = subprocess.check_output(args, stderr=subprocess.STDOUT)
    return out.decode("utf-8", "ignore").strip()

def get_commit_hash(repo: str) -> str:
    try:
        return sh("git", "-C", repo, "rev-parse", "HEAD")
    except Exception:
        return "unknown"

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__"}

ALLOW_EXT = {".py", ".md", ".txt", ".json", ".yaml", ".yml"}

def collect_files(repo: str):
    files = []
    for root, dirs, fnames in os.walk(repo):
        # ตัดโฟลเดอร์ที่ไม่ต้องการ
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in fnames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in ALLOW_EXT:
                files.append(os.path.join(root, fn))
    return files

def read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""

def chunk_file(path: str, n: int = 1000, overlap: int = 100):
    """คืน (start,end,text) เป็นชิ้น ๆ สำหรับทำ embedding"""
    s = read_text(path)
    L = len(s)
    i = 0
    while i < L:
        j = min(L, i + n)
        yield (i, j, s[i:j])
        i += max(1, n - overlap)

def http_post(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))

def embed(text: str):
    """เรียก Ollama embeddings (bge-m3) -> list[float] ขนาด 1024"""
    resp = http_post(f"{OLLAMA}/api/embeddings", {"model": "bge-m3", "prompt": text})
    emb = resp.get("embedding")
    if not isinstance(emb, list):
        raise RuntimeError(f"bad embedding response: {resp}")
    return emb


# วางแทนฟังก์ชัน upsert หรือ upsert_batch เดิม
def upsert_points(points):
    """
    points: list ของ dict รูปแบบ {"id": <int|uuid|str>, "vector": [...], "payload": {...}}
    ส่งแบบ {"points": [...]} ไป Qdrant (เหมือนที่เทสผ่านแล้ว)
    """
    import json, urllib.request
    body = {"points": points}
    req = urllib.request.Request(
        "http://127.0.0.1:6333/collections/code_rag/points?wait=true",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type":"application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))



# === add this back, near the bottom of index_repo.py ===
def upsert_points(points):
    """
    points: [{"id": <str|int>, "vector": [...], "payload": {...}}, ...]
    ส่งเป็น {"points":[...]} ให้ Qdrant (ฟอร์แมตที่ยืนยันแล้วว่าใช้ได้)
    """
    import json, urllib.request
    body = {"points": points}
    req = urllib.request.Request(
        "http://127.0.0.1:6333/collections/code_rag/points?wait=true",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    repo = REPO
    commit = get_commit_hash(repo)
    files = collect_files(repo)
    print(f"Repo: {repo}")
    print(f"Commit: {commit}")
    print(f"Files: {len(files)}")

    points = []
    total = 0

    for fpath in files:
        for start, end, text in chunk_file(fpath):
            vec = embed(text)
            pid = str(uuid.uuid4())  # ต้องมี import uuid ด้านบน
            pay = {
                "path": os.path.relpath(fpath, repo),
                "start": start,
                "end": end,
                "commit": commit,
            }
            points.append({"id": pid, "vector": vec, "payload": pay})

            if len(points) >= BATCH:
                resp = upsert_points(points)
                print("UPSERT status:", resp.get("status"))
                total += len(points)
                points = []

    if points:
        resp = upsert_points(points)
        print("UPSERT status:", resp.get("status"))
        total += len(points)

    print("Indexed chunks:", total)

if __name__ == "__main__":
    main()


