"""연습용 아바타: 원장님 영상을 등록하기 전에도 '아바타 자리'만 있는 그림으로
자막·배지·로고 합성이 어떻게 보이는지 시험할 수 있게 합니다.
"""
from pathlib import Path

from PIL import Image, ImageDraw

from .compose import get_font

DEMO_AVATARS = [
    {"id": "demo-landscape", "name": "연습용 아바타 (가로)", "kind": "photo", "orientation": "landscape",
     "preview_image": "/static/demo-landscape.png", "status": "demo", "demo": True},
    {"id": "demo-portrait", "name": "연습용 아바타 (세로)", "kind": "photo", "orientation": "portrait",
     "preview_image": "/static/demo-portrait.png", "status": "demo", "demo": True},
]


def is_demo(avatar_id):
    return str(avatar_id).startswith("demo-")


def demo_frame(W, H):
    img = Image.new("RGB", (W, H), (226, 232, 240))
    d = ImageDraw.Draw(img)
    # 은은한 세로 그라데이션 배경
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(232 - 30 * t), int(238 - 26 * t), int(246 - 16 * t)))
    s = min(W, H) / 1080
    cx = W // 2
    # 사람 모양 실루엣
    head_r = int(110 * s)
    head_cy = int(H * 0.40)
    d.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=(148, 163, 184))
    body_w = int(330 * s)
    d.rounded_rectangle([cx - body_w, head_cy + head_r + int(30 * s), cx + body_w, H + int(200 * s)],
                        radius=int(160 * s), fill=(255, 255, 255))
    d.rounded_rectangle([cx - int(40 * s), head_cy + head_r + int(30 * s), cx + int(40 * s), H],
                        radius=int(20 * s), fill=(37, 99, 235))
    f = get_font("default", 700, 34 * s)
    label = "연습 모드 · 실제 영상에서는 이 자리에 원장님 아바타가 나옵니다"
    tw = d.textlength(label, font=f)
    if tw > W * 0.9:
        label = "연습 모드 · 아바타 자리"
        tw = d.textlength(label, font=f)
    d.text(((W - tw) / 2, int(H * 0.22) - head_r), label, font=f, fill=(71, 85, 105))
    return img


def demo_source(avatar_id, workdir):
    """연습용 아바타의 화면 그림 (사진 아바타처럼 반복해서 씀)"""
    W, H = (1920, 1080) if avatar_id == "demo-landscape" else (1080, 1920)
    p = Path(workdir) / f"{avatar_id}.png"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        demo_frame(W, H).save(p)
    return str(p)


def make_demo_previews(static_dir):
    """화면에 보여 줄 연습 아바타 미리보기 그림"""
    for name, (W, H) in {"demo-landscape.png": (640, 360), "demo-portrait.png": (360, 640)}.items():
        p = Path(static_dir) / name
        if not p.exists():
            demo_frame(W, H).save(p)
