"""
Height Map 계약 (H Contract) — 코드 상의 단일 진실 공급원.

문서: docs/height-map-contract.md
이 모듈의 상수/함수는 A3(파이프라인)·A4(웹은 백엔드 경유)·A5(백엔드)·결선(FPGA)이
전부 공유한다. 값을 바꾸려면 여기서만 바꾸고 docs 버전을 올린다.
"""
from __future__ import annotations
import numpy as np

# ── 격자 (결선 FPGA 실제 핀 개수와 동일해야 함) ───────────────────────────
GRID_COLS: int = 48          # x, 가로
GRID_ROWS: int = 32          # y, 세로
N_PINS: int = GRID_COLS * GRID_ROWS

# ── 높이 양자화 ──────────────────────────────────────────────────────────
HEIGHT_LEVELS: int = 16      # 0..15
HEIGHT_BITS: int = 4         # 핀당 비트 수 (FPGA 직렬화용)
LEVELS_VERSION: str = "0.1"


def quantize(h_norm: np.ndarray) -> np.ndarray:
    """0..1 float 맵 → 0..15 정수 맵 (clamp)."""
    h = np.clip(h_norm, 0.0, 1.0)
    q = np.rint(h * (HEIGHT_LEVELS - 1)).astype(np.int16)
    return np.clip(q, 0, HEIGHT_LEVELS - 1)


def validate(H: np.ndarray) -> np.ndarray:
    """계약 위반 시 즉시 실패. 모든 H는 다운스트림 전달 전 이걸 통과해야 함."""
    if H.shape != (GRID_ROWS, GRID_COLS):
        raise ValueError(f"H shape {H.shape} != ({GRID_ROWS}, {GRID_COLS})")
    if H.min() < 0 or H.max() > HEIGHT_LEVELS - 1:
        raise ValueError(f"H values out of [0,{HEIGHT_LEVELS-1}]: {H.min()}..{H.max()}")
    return H


def to_json(H: np.ndarray, artwork_id: str, roi: dict | None = None) -> dict:
    """웹/백엔드 전송용 dict. data는 row-major 1차원 정수 배열."""
    validate(H)
    return {
        "artwork_id": artwork_id,
        "cols": GRID_COLS,
        "rows": GRID_ROWS,
        "levels": HEIGHT_LEVELS,
        "roi": roi or {"cx": 0.5, "cy": 0.5, "scale": 1.0},
        "data": H.astype(int).flatten(order="C").tolist(),  # row-major
    }


def from_json(payload: dict) -> np.ndarray:
    return validate(
        np.array(payload["data"], dtype=np.int16).reshape(payload["rows"], payload["cols"])
    )


# ── 결선(FPGA) 대비 — 본선 미연결, 값만 정렬 ─────────────────────────────
SYNC_BYTE = 0xA5


def pack_4bit(H: np.ndarray) -> bytes:
    """row-major 정수 H → 4-bit 패킹 페이로드 (2핀/바이트)."""
    validate(H)
    flat = H.astype(np.uint8).flatten(order="C")
    if flat.size % 2:                       # 홀수 핀이면 0 패딩
        flat = np.append(flat, 0)
    hi, lo = flat[0::2], flat[1::2]
    return bytes(((hi << 4) | (lo & 0x0F)).astype(np.uint8))


def to_uart_frame(H: np.ndarray) -> bytes:
    """[sync][cols][rows][levels][payload][checksum] — 결선 손승우가 최종 확정."""
    payload = pack_4bit(H)
    body = bytes([GRID_COLS & 0xFF, GRID_ROWS & 0xFF, HEIGHT_LEVELS & 0xFF]) + payload
    checksum = (sum(body) & 0xFF) ^ 0xFF
    return bytes([SYNC_BYTE]) + body + bytes([checksum])


if __name__ == "__main__":
    # 자가 점검: 합성 H 한 장으로 계약 라운드트립 확인
    rng = np.random.default_rng(0)
    H = quantize(rng.random((GRID_ROWS, GRID_COLS)))
    j = to_json(H, "selftest")
    assert (from_json(j) == H).all()
    frame = to_uart_frame(H)
    print(f"OK  pins={N_PINS}  json_data_len={len(j['data'])}  uart_frame={len(frame)}B")
