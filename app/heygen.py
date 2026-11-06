"""HeyGen API (v3) 연결.

공식 문서: https://developers.heygen.com
- 아바타 목록: GET  /v3/avatars/looks
- 목소리 목록: GET  /v3/voices
- 영상 만들기: POST /v3/videos           (비용이 드는 유일한 호출)
- 진행 확인:   GET  /v3/videos/{video_id}
- 계정·잔액:   GET  /v3/users/me

초보자 메모: API 키는 이 파일에 직접 쓰지 않습니다. 설정 화면에서 넣으면
data/app.db 에만 저장되고, 화면(브라우저)으로는 절대 보내지 않습니다.
"""

import httpx

from .config import HEYGEN_BASE


class HeyGenError(Exception):
    pass


def _req(key, method, path, timeout=30, **kw):
    """HeyGen 에 요청을 보내고 결과(JSON)를 돌려줍니다. 인터넷 문제도 알기 쉬운 문장으로 바꿉니다."""
    headers = {"x-api-key": key, "accept": "application/json", **kw.pop("headers", {})}
    try:
        with httpx.Client(base_url=HEYGEN_BASE, timeout=timeout, headers=headers) as c:
            r = c.request(method, path, **kw)
    except httpx.TimeoutException:
        raise HeyGenError("HeyGen 응답이 늦습니다. 잠시 뒤 다시 시도해 주세요.")
    except httpx.HTTPError as e:
        raise HeyGenError(f"HeyGen 서버에 연결하지 못했습니다. 인터넷 연결이나 병원 방화벽을 확인해 주세요. ({e.__class__.__name__})")
    return _check(r)


def _check(r: httpx.Response):
    if r.status_code < 400:
        return r.json()
    try:
        err = r.json().get("error") or {}
        msg = err.get("message") or r.text[:300]
    except Exception:
        msg = r.text[:300]
    if r.status_code == 401:
        raise HeyGenError("HeyGen API 키가 맞지 않습니다. 설정에서 키를 다시 확인해 주세요.")
    if r.status_code == 429:
        raise HeyGenError(f"HeyGen 요청이 너무 많습니다. 잠시 뒤 다시 시도합니다. ({msg})")
    if r.status_code == 403:
        raise HeyGenError(f"HeyGen 이 요청을 거절했습니다(403). API 사용 권한이나 요금제를 확인해 주세요. ({msg})")
    if r.status_code == 402:
        raise HeyGenError("HeyGen 잔액(크레딧)이 부족합니다. HeyGen 에서 충전해 주세요.")
    raise HeyGenError(f"HeyGen 오류 {r.status_code}: {msg}")


def _mask(s, keep=2):
    if not s:
        return ""
    if "@" in s:
        name, dom = s.split("@", 1)
        host, _, tld = dom.rpartition(".")
        return f"{name[:keep]}***@{host[:1]}***.{tld}"
    return s[:keep] + "***"


def get_user(key):
    d = _req(key, "GET", "/v3/users/me").get("data", {})
    bt = d.get("billing_type")
    balance, auto_reload = None, None
    if bt == "wallet" and d.get("wallet"):
        w = d["wallet"]
        cur = (w.get("currency") or "").upper()
        if w.get("remaining_balance") is not None:
            balance = f"{w['remaining_balance']:.2f} {cur}" if cur == "USD" else f"{w['remaining_balance']} {cur}"
        if w.get("auto_reload") is not None:
            auto_reload = bool(w["auto_reload"].get("enabled"))
    elif bt == "subscription" and d.get("subscription"):
        cr = (d["subscription"].get("credits") or {}).get("premium_credits") or {}
        if cr.get("remaining") is not None:
            balance = f"{cr['remaining']} 크레딧 ({d['subscription'].get('plan')})"
    elif bt == "usage_based" and d.get("usage_based"):
        u = d["usage_based"]
        if u.get("remaining_credits") is not None:
            balance = f"{u['remaining_credits']} 크레딧"
    return {
        "username": _mask(d.get("username")),
        "email": _mask(d.get("email")),
        "billing_type": bt,
        "balance": balance,
        "auto_reload": auto_reload,
    }


def _look(item, mine):
    w, h = item.get("image_width"), item.get("image_height")
    orient = item.get("preferred_orientation")
    if orient not in ("portrait", "landscape", "square"):
        orient = None
        if w and h:
            orient = "portrait" if h > w else "landscape"
    return {
        "id": item.get("id"),
        "name": item.get("name") or "이름 없음",
        "type": item.get("avatar_type"),
        "group_id": item.get("group_id"),
        "preview_image": item.get("preview_image_url"),
        "preview_video": item.get("preview_video_url"),
        "default_voice_id": item.get("default_voice_id"),
        "orientation": orient or "landscape",
        "gender": item.get("gender"),
        "status": item.get("status") or "completed",
        "mine": mine,
    }


def list_looks(key, ownership="private", token=None, limit=50):
    params = {"ownership": ownership, "limit": limit}
    if token:
        params["token"] = token
    d = _req(key, "GET", "/v3/avatars/looks", params=params)
    items = [_look(i, ownership == "private") for i in d.get("data", [])]
    items = [i for i in items if i["status"] == "completed"]
    return {"items": items, "next_token": d.get("next_token") if d.get("has_more") else None}


def list_voices(key, language=None, voice_type="public", limit=100):
    params = {"type": voice_type, "limit": limit}
    if language:
        params["language"] = language
    d = _req(key, "GET", "/v3/voices", params=params)
    out = []
    for v in d.get("data", []):
        if not v.get("available_engines"):
            continue  # 말을 만들 수 없는 목소리
        out.append({"id": v["voice_id"], "name": v.get("name"), "language": v.get("language"),
                    "gender": v.get("gender"), "preview": v.get("preview_audio_url")})
    return out


def create_video(key, *, avatar_id, script, voice_id, aspect, resolution, title,
                 background=None, callback_id=None, idempotency_key=None):
    """영상 생성 요청 (이때 HeyGen 비용이 듭니다). video_id 반환"""
    body = {
        "type": "avatar",
        "avatar_id": avatar_id,
        "script": script,
        "aspect_ratio": aspect,
        "resolution": resolution,
        "title": title[:100],
        "caption": {"file_format": "srt"},   # 말한 시점이 담긴 자막 파일을 같이 받음
    }
    if voice_id:
        body["voice_id"] = voice_id
    if background and background.get("type") == "color" and background.get("value"):
        body["background"] = {"type": "color", "value": background["value"]}
    elif background and background.get("type") == "image" and background.get("url"):
        body["background"] = {"type": "image", "url": background["url"]}
    if callback_id:
        body["callback_id"] = str(callback_id)
    # 프로그램이 중간에 꺼졌다 다시 요청해도 두 번 결제되지 않도록 Idempotency-Key 사용
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    d = _req(key, "POST", "/v3/videos", timeout=60, json=body, headers=headers)
    vid = (d.get("data") or {}).get("video_id")
    if not vid:
        raise HeyGenError("HeyGen 이 video_id 를 돌려주지 않았습니다.")
    return vid


def get_video(key, video_id):
    return _req(key, "GET", f"/v3/videos/{video_id}").get("data", {})


def download(url, path):
    try:
        with httpx.stream("GET", url, timeout=300, follow_redirects=True) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
    except httpx.HTTPError as e:
        raise HeyGenError(f"완성된 아바타 영상을 내려받지 못했습니다. 인터넷 연결을 확인한 뒤 「다시 시도」를 눌러 주세요. ({e.__class__.__name__})")


def fetch_text(url):
    r = httpx.get(url, timeout=60, follow_redirects=True)
    r.raise_for_status()
    r.encoding = r.encoding or "utf-8"
    return r.text
