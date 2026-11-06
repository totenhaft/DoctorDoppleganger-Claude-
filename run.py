"""프로그램 실행 파일.

    python run.py          → 이 PC 에서만 접속 (http://127.0.0.1:8000)
    python run.py --lan    → 병원 내부망의 다른 PC·휴대폰에서도 접속 가능

검은 명령창을 닫으면 프로그램이 꺼집니다. 영상 만드는 중에는 켜 두세요.
"""
import argparse
import os
import socket
import sys
import threading
import webbrowser

# 어느 폴더에서 실행하든 프로그램 폴더 기준으로 동작하게
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

if sys.version_info < (3, 10):
    sys.exit("파이썬 3.10 이상이 필요합니다. https://www.python.org 에서 새 버전을 설치해 주세요.")

try:
    import uvicorn
except ImportError:
    sys.exit("필요한 패키지가 없습니다. 먼저 이 명령을 실행해 주세요:  pip install -r requirements.txt")


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "이 PC 의 IP"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", action="store_true", help="병원 내부망에서 접속 허용")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    url = f"http://127.0.0.1:{a.port}"
    print("=" * 60)
    print(" Doctor Doppelganger · 진료안내 영상 자동화")
    print(f" 이 PC 에서 열기: {url}")
    if a.lan:
        print(f" 내부망에서 열기: http://{lan_ip()}:{a.port}")
    print(" 끄려면 이 창에서 Ctrl + C 를 누르거나 창을 닫으세요.")
    print("=" * 60)
    if not a.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
