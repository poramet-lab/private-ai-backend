# คู่มือการติดตั้งและใช้งาน (Deployment Guide)

เอกสารนี้สรุปขั้นตอนการติดตั้งและรันโปรเจกต์ `private-ai-backend` ทั้งหมดโดยใช้ Docker และ Docker Compose

## 1. สิ่งที่ต้องมี (Prerequisites)

- **Git:** สำหรับ Clone โปรเจกต์
- **Docker & Docker Compose:**
  - **Windows/Mac:** ติดตั้ง [Docker Desktop](https://www.docker.com/products/docker-desktop/)
  - **Linux (Ubuntu/Debian):** ติดตั้งผ่าน Terminal โดยทำตาม [คู่มืออย่างเป็นทางการของ Docker](https://docs.docker.com/engine/install/ubuntu/) ซึ่งจะติดตั้งทั้ง Docker Engine และ Docker Compose Plugin ให้พร้อมกัน
- **NVIDIA GPU (แนะนำ):** หากต้องการให้ Ollama ทำงานบน GPU ต้องติดตั้ง NVIDIA Container Toolkit

## 2. ขั้นตอนการติดตั้ง (Setup)

### 2.1 Clone โปรเจกต์

```bash
git clone <your-repository-url>
cd private-ai-backend
```

### 2.2 สร้างไฟล์ Environment (`.env`)

สร้างไฟล์ชื่อ `.env` ที่ root ของโปรเจกต์ แล้วคัดลอกเนื้อหาด้านล่างไปวาง

**สำคัญ:** เปลี่ยนค่า `SECRET_KEY` เป็นค่าใหม่ที่สุ่มขึ้นมาและคาดเดาได้ยาก

```env
SECRET_KEY="your-super-secret-and-long-random-string-for-production"
BACKEND_BASE_URL="http://127.0.0.1:8081"
QDRANT_URL="http://127.0.0.1:6333"
OLLAMA_URL="http://127.0.0.1:11435"
OPENAI_API_KEY="sk-..."
```

### 2.3 สร้างโฟลเดอร์ที่จำเป็น

สคริปต์ `ingest_api` จำเป็นต้องใช้โฟลเดอร์ `~/private-ai/projects` ในการจัดเก็บไฟล์ ให้สร้างโฟลเดอร์นี้ก่อน

```bash
mkdir -p ~/private-ai/projects
```

## 3. การรันโปรเจกต์ (Running the Project)

รันคำสั่งเดียวเพื่อเริ่มการทำงานของทุก Service (Backend, Qdrant, Ollama):

```bash
docker-compose up --build -d
```

- `--build`: สั่งให้ Docker สร้าง Image ของ Backend ใหม่ (ควรใช้ครั้งแรก หรือเมื่อมีการแก้ไขโค้ด Backend)
- `-d`: (Detached mode) รัน Container ทั้งหมดใน background

เมื่อรันสำเร็จ ระบบ Backend จะพร้อมใช้งานที่ `http://localhost:8081`

## 4. การหยุดการทำงาน

```bash
docker-compose down
```