# test_hash.py
from passlib.context import CryptContext
import sys

# ใช้การตั้งค่าเดียวกับใน auth_api.py
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# รหัสผ่านที่ต้องการทดสอบ
plain_password = "password"

# hash ที่เราต้องการตรวจสอบ (จากไฟล์ auth_config.py ล่าสุด)
hashed_password = "$2b$12$Jd.oOC5VIOMfXz5a925.d.V3bO8q.z/y9G2P.6K.Yq.a.b.c.d.e"

print(f"Python version: {sys.version}")
print(f"Testing hash: {hashed_password}")
print(f"Plain password: {plain_password}")
print("-" * 20)

try:
    # ลอง verify รหัสผ่าน
    is_valid = pwd_context.verify(plain_password, hashed_password)

    if is_valid:
        print("✅ SUCCESS: Hash is valid and matches the password.")
    else:
        print("❌ FAILED: Hash is valid, but does NOT match the password.")

except Exception as e:
    # ถ้าเกิดข้อผิดพลาด แสดงว่า hash มีปัญหา
    print(f"💥 ERROR: An exception occurred. The hash is likely malformed.")
    print(f"Exception Type: {type(e).__name__}")
    print(f"Exception Details: {e}")

