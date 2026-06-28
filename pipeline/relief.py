"""
A3 relief 처리 — 정면 depth/relief → 계약 H(0..15).

지금(Phase A, GPU 없음)은 depth estimation을 아직 안 붙였으므로,
end-to-end 슬라이스를 돌리기 위한 *합성 H 생성기*를 둔다.
Phase B에서 generate_synthetic_h() 를 실제 depth→relief 파이프라인으로 교체.

  TODO(A3): 배경 분리 → CPU depth estimation → relief(배경 평탄화/엣지 강조/bbox 정규화)
  TODO(B1): depth GPU 전환(큰 모델, 0.1~1초)
"""
from __future__ import annotations
import numpy as np
from . import contract as C


def generate_synthetic_h(kind: str = "dome", seed: int = 0) -> np.ndarray:
    """임시 합성 H. kind: dome(입체 유물 느낌) / face(부조 얼굴) / relief_edges(회화 분기)."""
    rows, cols = C.GRID_ROWS, C.GRID_COLS
    yy, xx = np.mgrid[0:rows, 0:cols].astype(float)
    cy, cx = (rows - 1) / 2, (cols - 1) / 2

    if kind == "face":
        # 중앙 얼굴(큰 돔) + 머리 위 관(상단 융기) — 사진 속 불상 머리 느낌
        r = np.sqrt(((xx - cx) / (cols * 0.32)) ** 2 + ((yy - cy + 2) / (rows * 0.38)) ** 2)
        h = np.clip(1 - r, 0, 1) ** 0.7
        crown = np.exp(-(((xx - cx) / (cols * 0.18)) ** 2 + ((yy - cy + rows * 0.34) / (rows * 0.10)) ** 2))
        h = np.maximum(h, crown * 0.85)
    elif kind == "relief_edges":
        # 회화 분기: 동심 윤곽선 relief
        r = np.sqrt(((xx - cx) / cols) ** 2 + ((yy - cy) / rows) ** 2)
        h = 0.5 + 0.5 * np.sin(r * 26)
        h *= np.clip(1 - r * 1.6, 0, 1)
    else:  # dome
        r = np.sqrt(((xx - cx) / (cols * 0.42)) ** 2 + ((yy - cy) / (rows * 0.42)) ** 2)
        h = np.clip(1 - r ** 2, 0, 1)

    return C.validate(C.quantize(h))


_REMBG_SESSION = None


def _remove_bg(img):
    """rembg로 배경 제거 → 피사체 alpha 마스크 포함 RGBA 반환. 실패 시 None."""
    global _REMBG_SESSION
    try:
        from rembg import remove, new_session
        if _REMBG_SESSION is None:
            _REMBG_SESSION = new_session("u2net")
        return remove(img.convert("RGBA"), session=_REMBG_SESSION)
    except Exception as e:
        print("[relief] rembg 실패, 배경제거 생략:", e)
        return None


def image_to_h(path: str, art_type: str = "3d") -> np.ndarray:
    """
    [Phase A — CPU] 업로드 사진 → 계약 H(0..15).

    1) rembg로 배경 제거 → 피사체만 남김 (다른 물체/배경이 핀으로 안 솟게)
    2) 피사체 실루엣을 솟아오르게 + 내부 밝기로 약한 relief
       - 2d(회화): 엣지(윤곽) 강조
    아직 진짜 depth가 아니라 실루엣+밝기 근사다. TODO(B1): depth estimation(GPU)로 교체.
    """
    from PIL import Image, ImageFilter, ImageOps

    rows, cols = C.GRID_ROWS, C.GRID_COLS
    src = ImageOps.exif_transpose(Image.open(path)).convert("RGB")

    cut = _remove_bg(src)
    if cut is not None:
        alpha = np.asarray(cut.resize((cols, rows)).split()[-1], dtype=float) / 255.0  # 피사체 마스크
        gray = np.asarray(cut.convert("L").resize((cols, rows)), dtype=float)
    else:
        alpha = np.ones((rows, cols))
        gray = np.asarray(src.convert("L").resize((cols, rows)), dtype=float)

    mask = alpha > 0.4  # 피사체 영역

    if art_type == "2d":
        edges = np.asarray(src.convert("L").filter(ImageFilter.FIND_EDGES).resize((cols, rows)), dtype=float)
        a = edges * (alpha if cut is not None else 1.0)
    else:
        # 피사체 내부 밝기 정규화 → 실루엣을 바닥에서 띄우고 내부 입체감 부여
        g = gray.copy()
        if mask.any():
            mn, mx = g[mask].min(), g[mask].max()
            g = (g - mn) / (mx - mn + 1e-6)
        a = alpha * (0.45 + 0.55 * np.clip(g, 0, 1))  # 실루엣 0.45 + 밝기 0.55
        a *= (alpha > 0.1)  # 배경 완전히 0

    a = np.clip(a, 0, None)
    if np.ptp(a) > 0:
        a = (a - a.min()) / (np.ptp(a) + 1e-6)
    return C.validate(C.quantize(a))


if __name__ == "__main__":
    for k in ("dome", "face", "relief_edges"):
        H = generate_synthetic_h(k)
        print(k, "→ H range", H.min(), H.max(), "shape", H.shape)
