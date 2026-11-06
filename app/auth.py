"""로그인, 비밀번호, 세션.

초보자 메모:
- 비밀번호는 원문을 저장하지 않고 '해시'(되돌릴 수 없게 섞은 값)만 저장합니다.
- 로그인하면 브라우저 쿠키에 무작위 세션 토큰이 들어가고, 12시간 뒤 만료됩니다.
"""
import hashlib
import hmac
import re
import secrets

from fastapi import HTTPException, Request

from .config import MAX_LOGIN_FAILS, MIN_PASSWORD_LEN, SESSION_HOURS
from .db import db, now, row

COOKIE = "dd_session"
_ITER = 310_000
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._@+\-]{2,63}$")


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), _ITER)
    return f"pbkdf2${_ITER}${salt}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), h)
    except Exception:
        return False


def password_problem(pw: str):
    """비밀번호 규칙 위반이면 이유 문장, 괜찮으면 None"""
    if len(pw or "") < MIN_PASSWORD_LEN:
        return f"비밀번호는 {MIN_PASSWORD_LEN}자 이상이어야 합니다."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "비밀번호에 영문과 숫자를 함께 넣어 주세요."
    return None


def normalize_username(u: str) -> str:
    return (u or "").strip().lower()


def account_count() -> int:
    with db() as c:
        return c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]


def create_account(username, password, role="staff", must_change=True):
    with db() as c:
        c.execute(
            "INSERT INTO accounts(username, pw_hash, role, status, must_change, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (username, hash_password(password), role,
             "pending" if must_change else "active", 1 if must_change else 0, now()),
        )


def new_session(username) -> str:
    token = secrets.token_urlsafe(32)
    with db() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
        c.execute("INSERT INTO sessions(token, username, expires_at) VALUES(?,?,?)",
                  (token, username, now() + SESSION_HOURS * 3600))
    return token


def end_sessions(username):
    with db() as c:
        c.execute("DELETE FROM sessions WHERE username=?", (username,))


def try_login(username, password):
    """(계정, 오류문장) 반환"""
    username = normalize_username(username)
    with db() as c:
        acc = row(c.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone())
        if not acc:
            return None, "아이디 또는 비밀번호가 맞지 않습니다."
        if acc["status"] == "disabled":
            return None, "사용이 중지된 계정입니다. 운영자에게 문의하세요."
        if acc["locked"]:
            return None, "로그인이 잠겼습니다. 운영자에게 잠금 해제를 요청하세요."
        if not verify_password(password, acc["pw_hash"]):
            fails = acc["failed_count"] + 1
            locked = 1 if fails >= MAX_LOGIN_FAILS else 0
            c.execute("UPDATE accounts SET failed_count=?, locked=? WHERE username=?",
                      (fails, locked, username))
            if locked:
                return None, f"비밀번호를 {MAX_LOGIN_FAILS}번 틀려 로그인이 잠겼습니다. 운영자에게 잠금 해제를 요청하세요."
            return None, f"아이디 또는 비밀번호가 맞지 않습니다. ({fails}/{MAX_LOGIN_FAILS})"
        c.execute("UPDATE accounts SET failed_count=0 WHERE username=?", (username,))
    return acc, None


def current_user(request: Request):
    """로그인 안 됐으면 None"""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with db() as c:
        s = c.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
        if not s or s["expires_at"] < now():
            return None
        acc = row(c.execute("SELECT username, role, status, must_change FROM accounts WHERE username=?",
                            (s["username"],)).fetchone())
    if not acc or acc["status"] == "disabled":
        return None
    return acc


def require_user(request: Request):
    acc = current_user(request)
    if not acc:
        raise HTTPException(401, "로그인이 필요합니다.")
    if acc["must_change"]:
        raise HTTPException(403, "먼저 새 비밀번호를 정해 주세요.")
    return acc


def require_operator(request: Request):
    acc = require_user(request)
    if acc["role"] != "operator":
        raise HTTPException(403, "운영자만 할 수 있습니다.")
    return acc
