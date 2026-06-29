"""
A1 — NC VARCO 클라이언트 (공식 스펙 기준).

인증: 헤더 `OPENAPI_KEY: <키>`  (Bearer 아님)
호스트: https://openapi.ai.nc.com

- image-to-3D : PNG → GLB. 비동기(requestId → inference/result 폴링 → model_url).
- text2sound  : 텍스트(≤200자) → 환경음/효과음 WAV(10초). ※ 낭독(TTS) 아님.

.env:
  VARCO_API_KEY=...
  VARCO_BASE_URL=https://openapi.ai.nc.com
"""
from __future__ import annotations
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

_BASE = (os.getenv("VARCO_BASE_URL") or "https://openapi.ai.nc.com").rstrip("/")
_KEY = os.getenv("VARCO_API_KEY", "")
_T2S_PATH = os.getenv("VARCO_TEXT2SOUND_PATH", "/sound/varco/v1/api/text2sound")
_I23D_PATH = os.getenv("VARCO_IMAGE_TO_3D_PATH", "/3d/varco/v1/image-to-3d")


def _headers() -> dict:
    if not _KEY:
        raise RuntimeError("VARCO_API_KEY 미설정 (.env 확인)")
    return {"OPENAPI_KEY": _KEY}


def available() -> bool:
    return bool(_KEY)


# ── image-to-3D: PNG → GLB bytes ─────────────────────────────────────────
def image_to_3d(png_path: str, *, face_type: str = "tri", face_num: int = 300000,
                texture: bool = True, seed: int = -1, poll_s: float = 1.0,
                timeout_s: float = 600) -> bytes:
    """단일 오브젝트 PNG(배경 단순 권장) → GLB 모델 bytes. 평균 1~2분."""
    print(f"  [VARCO] image-to-3D 요청 → {png_path}", flush=True)
    with open(png_path, "rb") as f:
        job = requests.post(
            _BASE + _I23D_PATH,
            headers=_headers(),
            files={"image": f},
            data={"target_face_type": face_type, "target_face_num": str(face_num),
                  "generate_texture": str(texture).lower(), "seed": str(seed)},
            timeout=120,
        ).json()
    request_id = job["requestId"]
    print(f"  [VARCO] requestId={request_id} — 처리 대기 중…", flush=True)
    deadline = time.time() + timeout_s
    t0 = time.time()
    polls = 0
    while time.time() < deadline:
        result = requests.get(f"{_BASE}/inference/result/{request_id}",
                              headers=_headers(), timeout=30).json()
        status = result.get("status")
        if status != "processing":
            if status in ("failed", "error"):
                raise RuntimeError(f"image-to-3d 실패: {result}")
            print(f"  [VARCO] 완료({status}) {time.time()-t0:.0f}s — GLB 다운로드", flush=True)
            return requests.get(result["model_url"], timeout=180).content   # GLB
        polls += 1
        if polls % 5 == 0:
            print(f"  [VARCO] …처리 중 {time.time()-t0:.0f}s", flush=True)
        time.sleep(poll_s)
    raise TimeoutError("image-to-3d 타임아웃")


def image_to_3d_to_file(png_path: str, out_glb: str, **kw) -> str:
    Path(out_glb).parent.mkdir(parents=True, exist_ok=True)
    Path(out_glb).write_bytes(image_to_3d(png_path, **kw))
    return out_glb


# ── text2sound: 텍스트 → 환경음/효과음 WAV (낭독 아님) ───────────────────
def text2sound(prompt: str, num_samples: int = 1) -> list[bytes]:
    """분위기음/효과음 생성. prompt ≤200자. WAV bytes 리스트 반환.
    응답 형식: [{"audio": "<base64 WAV>"}, ...]  (검증됨 2026-06)"""
    import base64
    r = requests.post(_BASE + _T2S_PATH, headers=_headers(),
                      json={"prompt": prompt[:200], "num_samples": num_samples}, timeout=120)
    r.raise_for_status()
    data = r.json()
    items = data if isinstance(data, list) else data.get("results", [data])
    out = []
    for it in items:
        b64 = it.get("audio") if isinstance(it, dict) else it
        if b64:
            out.append(base64.b64decode(b64))
    return out


def text2sound_to_file(prompt: str, out_path: str) -> str:
    out = text2sound(prompt, 1)
    if not out:
        raise RuntimeError("text2sound: 빈 응답")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(out[0])
    return out_path


if __name__ == "__main__":
    print("base:", _BASE, "| key:", "있음" if _KEY else "없음")
    if available():
        try:
            text2sound_to_file("도자기를 부드럽게 두드리는 맑은 소리", "/tmp/varco_amb.wav")
            print("text2sound OK → /tmp/varco_amb.wav")
        except Exception as e:
            print("text2sound 실패(스펙 확인 필요):", str(e)[:200])
