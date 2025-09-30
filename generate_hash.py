# generate_hash.py
from passlib.context import CryptContext

# ใช้การตั้งค่าเดียวกับใน auth_api.py
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

password_to_hash = "password"

# สร้าง hash
hashed_password = pwd_context.hash(password_to_hash)

print("--- HASH ที่ถูกต้องสำหรับรหัสผ่าน 'password' ---")
print(hashed_password)
print("-------------------------------------------------")
print("กรุณาคัดลอก hash ด้านบนไปใส่ในไฟล์ auth_config.py ครับ")

