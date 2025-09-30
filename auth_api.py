from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, Annotated
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
import os

from auth_config import PILOT_USERS
# Import a database session, the User model, and the password hashing function
from database import SessionLocal, User as DBUser, get_password_hash as db_get_password_hash

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Config ---
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set in the environment variables. Please create a .env file.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 day

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

# --- Password Hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def get_db():
    """Database dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_user_by_username(db: Session, username: str):
    """Helper function to get a user by username from the database"""
    return db.query(DBUser).filter(DBUser.username == username).first()

# --- User Model ---
class User(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- JWT Helpers ---
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- User fetching ---
def get_user_from_config(username: str):
    """ดึงข้อมูลผู้ใช้จากไฟล์ config สำหรับ pilot mode"""
    hashed_password = PILOT_USERS.get(username)
    if hashed_password:
        return {"username": username, "hashed_password": hashed_password}
    return None

# --- Endpoints ---

@router.post("/register")
async def register_user(user: User, db: Session = Depends(get_db)):
    """
    Endpoint สำหรับลงทะเบียนผู้ใช้ใหม่
    """
    db_user = get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = db_get_password_hash(user.password)
    new_user = DBUser(username=user.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {
        "username": new_user.username,
        "message": "User created successfully."
    }

@router.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Endpoint สำหรับ Login เพื่อขอ Access Token
    ใช้ `application/x-www-form-urlencoded`
    """
    user = get_user_by_username(db, username=form_data.username)
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="ไม่สามารถยืนยันตัวตนได้",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user_by_username(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    # คืนค่าเป็น dict เพื่อให้สอดคล้องกับส่วนอื่นๆ ที่อาจคาดหวัง dict
    return {
        "username": user.username
    }

async def get_user_from_token(token: str):
    """
    ฟังก์ชันสำหรับตรวจสอบ Token ที่ส่งมาทาง WebSocket (จาก Query Parameter)
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials from token",
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user_from_config(username=username)
    if user is None:
        raise credentials_exception
    return user

async def validate_token_for_ws(token: str) -> Optional[dict]:
    """
    ตรวจสอบ Token สำหรับ WebSocket โดยเฉพาะ จะไม่ raise HTTPException
    แต่จะคืนค่า None หาก Token ไม่ถูกต้อง
    """
    db = SessionLocal()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        user = get_user_by_username(db, username=username)
        if user:
            # คืนค่าเป็น dict เพื่อให้ caller (main.py) ใช้งานได้
            return {"username": user.username}
        return None
    except JWTError:
        return None
    except Exception:
        return None
    finally:
        db.close()

async def get_current_active_user(current_user: Annotated[dict, Depends(get_current_user)]):
    # ในอนาคตอาจเพิ่มการเช็คสถานะ 'disabled' ของ user ที่นี่
    return current_user
