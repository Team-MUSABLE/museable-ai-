"""
A5 백엔드 — FastAPI 얇은 슬라이스.

지금은 A3 합성 H를 그대로 서빙해 A4(웹 핀 뷰) 끝단을 돌린다.
Phase A/B에서 실제 작품 등록·DB·캐싱·오디오로 확장.

실행:
  uvicorn backend.main:app --reload --port 8000
  → http://localhost:8000          (웹 핀 뷰)
  → http://localhost:8000/api/artworks
"""
from __future__ import annotations
from pathlib import Path

import uuid

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from pipeline import contract as C
from pipeline.relief import generate_synthetic_h, image_to_h

_DATA = Path(__file__).resolve().parent.parent / "data" / "artworks"
_DATA.mkdir(parents=True, exist_ok=True)
_H_CACHE: dict[str, list] = {}   # 업로드 작품의 H (image_to_h 결과). TODO(A5): DB로 교체

app = FastAPI(title="museable API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 데모 작품 카탈로그 (A7) — Phase A에서 실제 메타/사진으로 교체
ARTWORKS = [
    {"id": "buddha_01", "title": "금동 반가사유상", "kind": "face",
     "era": "삼국시대 7세기", "type": "3d", "material": "금동"},
    {"id": "celadon_01", "title": "청자 상감운학문 매병", "kind": "dome",
     "era": "고려 12세기", "type": "3d", "material": "청자(상감)"},
    {"id": "ssireum_01", "title": "김홍도 「씨름」", "kind": "relief_edges",
     "era": "조선 18세기", "type": "2d", "material": "지본담채"},
]
_DOCENT_CACHE: dict[str, str] = {}   # TODO(A5): DB 캐싱으로 교체
_BY_ID = {a["id"]: a for a in ARTWORKS}


@app.get("/api/artworks")
def list_artworks():
    return [{k: a[k] for k in ("id", "title", "era", "type")} for a in ARTWORKS]


@app.post("/api/artworks")
async def register_artwork(
    title: str = Form(...),
    era: str = Form(""),
    type: str = Form("3d"),          # "3d" | "2d"
    image: UploadFile = File(...),
):
    """A5 작품 등록 — 사진 업로드 → CPU relief 로 H 생성·캐싱."""
    aid = "up_" + uuid.uuid4().hex[:8]
    ext = (Path(image.filename or "").suffix or ".jpg").lower()
    dst = _DATA / f"{aid}{ext}"
    dst.write_bytes(await image.read())
    try:
        H = image_to_h(str(dst), art_type=type)   # TODO(B1): depth(GPU)로 교체
    except Exception as e:
        raise HTTPException(400, f"이미지 처리 실패: {e}")
    _H_CACHE[aid] = H.astype(int).flatten().tolist()
    art = {"id": aid, "title": title, "era": era, "type": type, "material": ""}
    ARTWORKS.append(art); _BY_ID[aid] = art
    return {k: art[k] for k in ("id", "title", "era", "type")}


@app.delete("/api/artworks/{artwork_id}")
def delete_artwork(artwork_id: str):
    art = _BY_ID.pop(artwork_id, None)
    if not art:
        raise HTTPException(404, "unknown artwork")
    ARTWORKS[:] = [a for a in ARTWORKS if a["id"] != artwork_id]
    _DOCENT_CACHE.pop(artwork_id, None)
    _H_CACHE.pop(artwork_id, None)
    for f in _DATA.glob(f"{artwork_id}.*"):   # 업로드 이미지 파일 정리
        f.unlink(missing_ok=True)
    return {"deleted": artwork_id}


@app.get("/api/artworks/{artwork_id}/heightmap")
def heightmap(artwork_id: str):
    art = _BY_ID.get(artwork_id)
    if not art:
        raise HTTPException(404, "unknown artwork")
    if artwork_id in _H_CACHE:                      # 업로드 작품: 사진에서 만든 H
        import numpy as np
        H = np.array(_H_CACHE[artwork_id], dtype=np.int16).reshape(C.GRID_ROWS, C.GRID_COLS)
    else:                                           # 데모 3점: 합성 H (A3 진짜 파이프라인 전까지)
        H = generate_synthetic_h(art["kind"])
    return C.to_json(H, artwork_id)


@app.get("/api/artworks/{artwork_id}/docent")
def docent(artwork_id: str):
    art = _BY_ID.get(artwork_id)
    if not art:
        raise HTTPException(404, "unknown artwork")
    if artwork_id not in _DOCENT_CACHE:
        try:
            from ai.exaone import generate_docent
            from rag.store import context_for
            ctx, sources = context_for(artwork_id, f"{art['title']} 형태 특징 촉각 도슨트", k=4)
            _DOCENT_CACHE[artwork_id] = {
                "text": generate_docent(art, context=ctx),
                "sources": sources,
                "grounded": bool(ctx),
            }
        except Exception as e:
            raise HTTPException(502, f"EXAONE 호출 실패: {e}")
    return {"artwork_id": artwork_id, **_DOCENT_CACHE[artwork_id]}


class _Q(__import__("pydantic").BaseModel):
    question: str


@app.post("/api/artworks/{artwork_id}/ask")
def ask(artwork_id: str, body: _Q):
    art = _BY_ID.get(artwork_id)
    if not art:
        raise HTTPException(404, "unknown artwork")
    try:
        from ai.exaone import answer_question
        from rag.store import context_for
        ctx, sources = context_for(artwork_id, body.question, k=4)
        return {"answer": answer_question(art, body.question, context=ctx),
                "sources": sources, "grounded": bool(ctx)}
    except Exception as e:
        raise HTTPException(502, f"EXAONE 호출 실패: {e}")


# 웹 정적 파일 마운트 (맨 마지막)
_WEB = Path(__file__).resolve().parent.parent / "web"
if _WEB.exists():
    app.mount("/", StaticFiles(directory=str(_WEB), html=True), name="web")
