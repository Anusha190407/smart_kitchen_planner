import hmac
import hashlib
import base64
import json
import time
import os
import secrets
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.database import get_db

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "smart-kitchen-planner-super-secret-key-2026")
ALGORITHM = "HS256"
TOKEN_EXPIRE_SECONDS = 7 * 24 * 3600  # 7 days

security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"pbkdf2:sha256:100000${salt}${key.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False
        meta, salt, stored_hash = parts
        _, hash_name, iterations_str = meta.split(":")
        iterations = int(iterations_str)
        key = hashlib.pbkdf2_hmac(hash_name, plain_password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return hmac.compare_digest(key.hex(), stored_hash)
    except Exception:
        return False

def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def base64url_decode(data: str) -> bytes:
    padding = "=" * (4 - (len(data) % 4)) if len(data) % 4 != 0 else ""
    return base64.urlsafe_b64decode((data + padding).encode("utf-8"))

def create_jwt_token(payload: dict) -> str:
    header = {"typ": "JWT", "alg": ALGORITHM}
    header_json = json.dumps(header, separators=(",", ":")).encode("utf-8")
    header_b64 = base64url_encode(header_json)
    
    payload_copy = payload.copy()
    payload_copy["exp"] = int(time.time()) + TOKEN_EXPIRE_SECONDS
    payload_copy["iat"] = int(time.time())
    payload_json = json.dumps(payload_copy, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64url_encode(payload_json)
    
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = base64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def decode_jwt_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Invalid token format")
    header_b64, payload_b64, sig_b64 = parts
    
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_sig = base64url_decode(sig_b64)
    
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise HTTPException(status_code=401, detail="Invalid token signature")
        
    payload_bytes = base64url_decode(payload_b64)
    payload = json.loads(payload_bytes.decode("utf-8"))
    
    if payload.get("exp", 0) < time.time():
        raise HTTPException(status_code=401, detail="Token has expired")
        
    return payload

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    token = credentials.credentials
    payload = decode_jwt_token(token)
    user_id = payload.get("user_id")
    restaurant_id = payload.get("restaurant_id")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT u.id, u.email, u.restaurant_id, r.name as restaurant_name, r.last_updated FROM users u JOIN restaurants r ON u.restaurant_id = r.id WHERE u.id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="User account not found")
        return dict(row)
