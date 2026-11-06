"""입모양 엔진 (MuseTalk 1.5, MIT 라이선스) — 엔진 전용 가상환경(engines/.venv)에서 실행됩니다.

    python lipsync_musetalk.py prepare --src 원본.mp4 --out 아바타폴더 [--ffmpeg ffmpeg경로]
    python lipsync_musetalk.py infer   --avatar 아바타폴더 --audio 음성.wav --out 결과.mp4 [--ffmpeg ffmpeg경로]

prepare: 원장님 영상(또는 사진)에서 얼굴 위치·입 주변 마스크·잠재값을 미리 계산해 둡니다 (아바타마다 한 번).
infer:   새 음성에 맞춰 입모양만 다시 그려 mp4 를 만듭니다 (영상마다).

진행 상황은 'PROGRESS 0.42 설명' 줄로, 결과는 'RESULT {json}' 줄로 출력합니다.
웹 프로그램(app/engines.py)이 이 줄을 읽어 화면에 보여 줍니다.

MuseTalk 원본 코드: https://github.com/TMElyralab/MuseTalk  (engines/MuseTalk 에 설치됨)
원본과 다른 점: 얼굴 랜드마크(DWPose)를 mmpose 대신 ONNX 로 돌려 윈도우 설치를 쉽게 했습니다.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MUSE = HERE / "MuseTalk"
FPS = 25


def say(p, msg=""):
    print(f"PROGRESS {max(0.0, min(1.0, p)):.3f} {msg}", flush=True)


def result(**kw):
    print("RESULT " + json.dumps(kw, ensure_ascii=False), flush=True)


def fail(msg):
    print("ERROR " + msg, flush=True)
    sys.exit(2)


def setup_paths():
    if not (MUSE / "musetalk").exists():
        fail("MuseTalk 코드가 없습니다. engines\\install 을 먼저 실행해 주세요.")
    os.chdir(MUSE)  # MuseTalk 은 ./models/... 상대경로로 가중치를 찾습니다
    sys.path.insert(0, str(MUSE))
    sys.path.insert(0, str(MUSE / "musetalk" / "utils"))


# ---------------------------------------------------------------- 얼굴 랜드마크 (DWPose ONNX)
class DWPoseOnnx:
    """DWPose(전신 133점) ONNX 모델. 얼굴 68점(23~90번)만 씁니다. CPU 로 돌려도 아바타당 한 번이라 충분합니다."""

    def __init__(self, onnx_path):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name
        self.size = (288, 384)  # (w, h)
        import numpy as np
        self.mean = np.array([123.675, 116.28, 103.53], dtype="float32")
        self.std = np.array([58.395, 57.12, 57.375], dtype="float32")

    def __call__(self, img_bgr):
        import cv2
        import numpy as np
        h, w = img_bgr.shape[:2]
        center = np.array([w / 2, h / 2], dtype=np.float32)
        scale = np.array([w, h], dtype=np.float32) * 1.25
        aspect = self.size[0] / self.size[1]
        if scale[0] > scale[1] * aspect:
            scale[1] = scale[0] / aspect
        else:
            scale[0] = scale[1] * aspect
        # mmpose 와 같은 방식의 아핀 변환
        src = np.array([center, center + [0, -scale[0] * 0.5], [0, 0]], dtype=np.float32)
        d = src[0] - src[1]
        src[2] = src[1] + np.array([-d[1], d[0]])
        dw, dh = self.size
        dst = np.array([[dw * 0.5, dh * 0.5], [dw * 0.5, dh * 0.5 - dw * 0.5], [0, 0]], dtype=np.float32)
        d = dst[0] - dst[1]
        dst[2] = dst[1] + np.array([-d[1], d[0]])
        M = cv2.getAffineTransform(src, dst)
        crop = cv2.warpAffine(img_bgr, M, (dw, dh), flags=cv2.INTER_LINEAR)
        x = (cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) - self.mean) / self.std
        x = x.transpose(2, 0, 1)[None]
        simcc_x, simcc_y = self.sess.run(None, {self.inp: x})
        xs = simcc_x[0].argmax(axis=1).astype(np.float32) / 2.0
        ys = simcc_y[0].argmax(axis=1).astype(np.float32) / 2.0
        pts = np.stack([xs, ys], axis=1)
        pts = pts / np.array(self.size, dtype=np.float32) * scale + center - scale / 2
        return pts  # (133, 2)


def face_box(landmarks, det_box, extra_margin=10, frame_h=None):
    """MuseTalk preprocessing.get_landmark_and_bbox 와 같은 규칙으로 입 주변 상자 계산 (v1.5 여백 포함)"""
    import numpy as np
    lm = landmarks[23:91].astype(np.int32)
    half = lm[29].copy()
    half_dist = int(np.max(lm[:, 1]) - half[1])
    upper = max(0, int(half[1] - half_dist))
    x1, y1, x2, y2 = int(np.min(lm[:, 0])), upper, int(np.max(lm[:, 0])), int(np.max(lm[:, 1]))
    if y2 - y1 <= 0 or x2 - x1 <= 0 or x1 < 0:
        x1, y1, x2, y2 = det_box
    y2 = y2 + extra_margin
    if frame_h:
        y2 = min(y2, frame_h)
    return [int(x1), int(y1), int(x2), int(y2)]


# ---------------------------------------------------------------- 모델 불러오기
def load_models(device, need_unet=True):
    import torch
    from musetalk.utils.utils import load_all_model
    vae, unet, pe = load_all_model(
        unet_model_path=os.path.join("models", "musetalkV15", "unet.pth"),
        vae_type="sd-vae",
        unet_config=os.path.join("models", "musetalkV15", "musetalk.json"),
        device=device,
    )
    half = device.type == "cuda"
    if half:
        pe, vae.vae, unet.model = pe.half(), vae.vae.half(), unet.model.half()
    pe, vae.vae, unet.model = pe.to(device), vae.vae.to(device), unet.model.to(device)
    return vae, unet, pe


# ---------------------------------------------------------------- prepare
def prepare(src, out, ffmpeg="ffmpeg"):
    import cv2
    import numpy as np
    import torch
    out = Path(out).resolve()
    src = Path(src).resolve()
    setup_paths()
    (out / "frames").mkdir(parents=True, exist_ok=True)
    (out / "masks").mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    say(0.02, "원본 영상을 읽고 있습니다")
    frames = []
    if src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        img = cv2.imread(str(src))
        if img is None:
            fail("사진 파일을 읽지 못했습니다.")
        frames = [img]
    else:
        cap = cv2.VideoCapture(str(src))
        while True:
            ok, f = cap.read()
            if not ok:
                break
            frames.append(f)
        cap.release()
    if not frames:
        fail("영상에서 화면을 읽지 못했습니다.")
    H, W = frames[0].shape[:2]

    say(0.05, "얼굴 찾기 모델을 불러오고 있습니다")
    from face_detection import FaceAlignment, LandmarksType
    fa = FaceAlignment(LandmarksType._2D, flip_input=False, device=str(device))
    pose = DWPoseOnnx(Path("models") / "dwpose" / "dw-ll_ucoco_384.onnx")

    coords, keep = [], []
    n = len(frames)
    k = min(1.0, 960.0 / W)  # 얼굴 찾기는 줄인 화면에서 (빠르게), 좌표는 원래 크기로 되돌림
    for i, f in enumerate(frames):
        small = cv2.resize(f, (int(W * k), int(H * k))) if k < 1 else f
        det = fa.get_detections_for_batch(np.asarray([small]))[0]
        if det is None:
            continue
        det = tuple(int(v / k) for v in det)
        lm = pose(f)
        coords.append(face_box(lm, det, extra_margin=10, frame_h=H))
        keep.append(i)
        if i % 10 == 0:
            say(0.05 + 0.45 * i / n, f"얼굴 위치 찾는 중 {i + 1}/{n}")
    if len(keep) < max(1, int(n * 0.7)):
        fail(f"얼굴을 찾지 못한 화면이 많습니다 ({n - len(keep)}/{n}). 정면에서 얼굴이 크게 나오게 다시 찍어 주세요.")
    frames = [frames[i] for i in keep]
    del fa

    say(0.52, "입모양 모델을 불러오고 있습니다")
    vae, _, _ = load_models(device)
    from musetalk.utils.face_parsing import FaceParsing
    from musetalk.utils.blending import get_image_prepare_material
    fp = FaceParsing(left_cheek_width=90, right_cheek_width=90)

    latents, mask_boxes = [], []
    n = len(frames)
    for i, (f, (x1, y1, x2, y2)) in enumerate(zip(frames, coords)):
        crop = cv2.resize(f[y1:y2, x1:x2], (256, 256), interpolation=cv2.INTER_LANCZOS4)
        with torch.no_grad():
            latents.append(vae.get_latents_for_unet(crop).cpu())
        mask, crop_box = get_image_prepare_material(f, [x1, y1, x2, y2], fp=fp, mode="jaw")
        cv2.imwrite(str(out / "masks" / f"{i:05d}.png"), mask)
        cv2.imwrite(str(out / "frames" / f"{i:05d}.jpg"), f, [cv2.IMWRITE_JPEG_QUALITY, 95])
        mask_boxes.append([int(v) for v in crop_box])
        if i % 5 == 0:
            say(0.55 + 0.43 * i / n, f"입 주변 준비 중 {i + 1}/{n}")

    torch.save(latents, out / "latents.pt")
    info = {"version": 1, "fps": FPS, "frames": n, "width": W, "height": H,
            "coords": coords, "mask_boxes": mask_boxes, "created": time.time()}
    (out / "avatar.json").write_text(json.dumps(info), encoding="utf-8")
    say(1.0, "아바타 준비를 마쳤습니다")
    result(frames=n, width=W, height=H)


# ---------------------------------------------------------------- infer
def infer(avatar, audio, out, ffmpeg="ffmpeg", batch=8):
    import cv2
    import numpy as np
    import torch
    from transformers import WhisperModel
    avatar = Path(avatar).resolve()
    audio = str(Path(audio).resolve())
    out = str(Path(out).resolve())
    setup_paths()
    info = json.loads((avatar / "avatar.json").read_text(encoding="utf-8"))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    say(0.02, "입모양 모델을 불러오고 있습니다")
    vae, unet, pe = load_models(device)
    from musetalk.utils.audio_processor import AudioProcessor
    from musetalk.utils.blending import get_image_blending
    from musetalk.utils.utils import datagen
    dtype = unet.model.dtype
    ap = AudioProcessor(feature_extractor_path=os.path.join("models", "whisper"))
    whisper = WhisperModel.from_pretrained(os.path.join("models", "whisper")).to(device=device, dtype=dtype).eval()
    whisper.requires_grad_(False)

    say(0.08, "음성을 분석하고 있습니다")
    feats, length = ap.get_audio_feature(audio, weight_dtype=dtype)
    with torch.no_grad():
        chunks = ap.get_whisper_chunk(feats, device, dtype, whisper, length, fps=FPS,
                                      audio_padding_length_left=2, audio_padding_length_right=2)
    del whisper
    total = len(chunks)

    lat = torch.load(avatar / "latents.pt")
    n = len(lat)
    cyc = list(range(n)) + list(range(n - 1, -1, -1))  # 앞으로 갔다 거꾸로 돌아오며 자연스럽게 반복
    lat_cycle = [lat[i] for i in cyc]
    W, H = info["width"], info["height"]

    enc = subprocess.Popen(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", out],
        stdin=subprocess.PIPE)
    timesteps = torch.tensor([0], device=device)
    frame_cache = {}

    def frame(i):
        k = cyc[i % len(cyc)]
        if k not in frame_cache:
            if len(frame_cache) > 64:
                frame_cache.clear()
            frame_cache[k] = (cv2.imread(str(avatar / "frames" / f"{k:05d}.jpg")),
                              cv2.imread(str(avatar / "masks" / f"{k:05d}.png"), cv2.IMREAD_GRAYSCALE))
        return k, frame_cache[k]

    done = 0
    t0 = time.time()
    with torch.no_grad():
        for wb, lb in datagen(chunks, lat_cycle, batch, device=device):
            feat = pe(wb.to(device))
            pred = unet.model(lb.to(device=device, dtype=dtype), timesteps, encoder_hidden_states=feat).sample
            recon = vae.decode_latents(pred.to(dtype=vae.vae.dtype))
            for face in recon:
                k, (ori, mask) = frame(done)
                x1, y1, x2, y2 = info["coords"][k]
                try:
                    face = cv2.resize(face.astype(np.uint8), (x2 - x1, y2 - y1))
                    img = get_image_blending(ori.copy(), face, [x1, y1, x2, y2], mask, info["mask_boxes"][k])
                except Exception:
                    img = ori
                enc.stdin.write(np.ascontiguousarray(img).tobytes())
                done += 1
            el = time.time() - t0
            left = el / max(done, 1) * (total - done)
            say(0.1 + 0.88 * done / total, f"입모양 맞추는 중 {done}/{total} · 남은 시간 약 {int(left // 60)}분 {int(left % 60)}초")
    enc.stdin.close()
    if enc.wait() != 0:
        fail("영상 저장(ffmpeg)에 실패했습니다.")
    say(1.0, "입모양 맞추기를 마쳤습니다")
    result(frames=done, seconds=round(done / FPS, 2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--src", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--ffmpeg", default="ffmpeg")
    i = sub.add_parser("infer")
    i.add_argument("--avatar", required=True)
    i.add_argument("--audio", required=True)
    i.add_argument("--out", required=True)
    i.add_argument("--ffmpeg", default="ffmpeg")
    i.add_argument("--batch", type=int, default=8)
    a = ap.parse_args()
    try:
        if a.cmd == "prepare":
            prepare(a.src, a.out, a.ffmpeg)
        else:
            infer(a.avatar, a.audio, a.out, a.ffmpeg, a.batch)
    except SystemExit:
        raise
    except Exception as e:  # 그래픽카드 메모리 부족 등
        import traceback
        traceback.print_exc()
        msg = str(e)
        if "out of memory" in msg.lower():
            msg = "그래픽카드 메모리가 부족합니다. 다른 프로그램(게임·영상 편집 등)을 끄고 다시 시도해 주세요."
        fail(msg[:500])


if __name__ == "__main__":
    main()
