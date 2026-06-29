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
DEMOS = [
    {"id": "buddha_01", "title": "금동 반가사유상", "kind": "face",
     "era": "삼국시대 7세기", "type": "3d", "material": "금동",
     "ambience": "고요한 사찰 법당, 멀리서 울리는 풍경 소리와 은은한 정적"},
    {"id": "celadon_01", "title": "청자 상감운학문 매병", "kind": "dome",
     "era": "고려 12세기", "type": "3d", "material": "청자(상감)",
     "ambience": "도자기 표면을 손끝으로 부드럽게 두드리는 맑고 청아한 소리"},
    {"id": "ssireum_01", "title": "김홍도 「씨름」", "kind": "relief_edges",
     "era": "조선 18세기", "type": "2d", "material": "지본담채",
     "ambience": "조선 장터 씨름판, 시끌벅적한 구경꾼들의 함성과 웃음"},
]
ARTWORKS = [dict(a) for a in DEMOS]
_BY_ID = {a["id"]: a for a in ARTWORKS}
_DOCENT_CACHE: dict[str, dict] = {}

# ── 영속 복원: SQLite 에 저장된 등록 작품/H/도슨트 불러오기 ──────────────
from . import db as _db
_db.init()
for _r in _db.load_all():
    _aid = _r["id"]
    if _aid in _BY_ID:                       # 데모: 저장된 필드/H로 보강
        for _k in ("title", "era", "type", "material", "ambience"):
            if _r.get(_k):
                _BY_ID[_aid][_k] = _r[_k]
    else:                                    # 업로드 작품 복원
        _art = {_k: _r[_k] for _k in ("id", "title", "era", "type", "material", "ambience")}
        ARTWORKS.append(_art); _BY_ID[_aid] = _art
    if _r["_h"]:
        _H_CACHE[_aid] = _r["_h"]
    if _r["_docent"]:
        _DOCENT_CACHE[_aid] = _r["_docent"]


def _has_real_image(aid: str) -> bool:
    return aid in _H_CACHE or any(_DATA.glob(f"{aid}.png")) \
        or any(_DATA.glob(f"{aid}.jpg")) or any(_DATA.glob(f"{aid}.jpeg"))


@app.get("/api/artworks")
def list_artworks():
    return [{**{k: a[k] for k in ("id", "title", "era", "type")},
             "real": _has_real_image(a["id"])} for a in ARTWORKS]


@app.post("/api/artworks")
async def register_artwork(
    title: str = Form(...),
    era: str = Form(""),
    type: str = Form("3d"),          # "3d" | "2d"
    image: UploadFile = File(...),
):
    """A5 작품 등록 — 사진 업로드 → CPU relief 로 H 생성·캐싱."""
    # 같은 제목이 이미 있으면 새로 만들지 않고 재사용(중복 방지)
    norm = (title or "").strip()
    existing = next((a for a in ARTWORKS if a.get("title", "").strip() == norm and norm), None)
    reuse = existing is not None
    aid = existing["id"] if reuse else "up_" + uuid.uuid4().hex[:8]
    ext = (Path(image.filename or "").suffix or ".jpg").lower()
    # 재사용 시 이전 이미지/캐시 정리(새 사진으로 교체)
    if reuse:
        for f in _DATA.glob(f"{aid}.*"):
            f.unlink(missing_ok=True)
        _DOCENT_CACHE.pop(aid, None); _H_CACHE.pop(aid, None)
        (Path(__file__).resolve().parent.parent / "audio_cache" / f"{aid}_ambience.wav").unlink(missing_ok=True)
    dst = _DATA / f"{aid}{ext}"
    dst.write_bytes(await image.read())
    notes = []
    print(f"\n[등록] {aid} '{title}' ({type}) — 사진 {dst.name} 수신 ({'기존 작품 재사용' if reuse else '새 작품'})", flush=True)

    # 1) 배경 제거 → 단일 오브젝트 PNG (VARCO image-to-3D 권장 입력)
    from PIL import Image
    from pipeline.relief import _remove_bg, image_to_h
    print("[등록] 1/3 배경 제거(rembg)…", flush=True)
    clean_png = _DATA / f"{aid}_clean.png"
    cut = _remove_bg(Image.open(dst))
    (cut or Image.open(dst).convert("RGBA")).save(clean_png)
    print(f"[등록]     배경 제거 {'성공' if cut is not None else '생략(원본 사용)'}", flush=True)

    # 2) 형태 H: VARCO 3D 있으면 실제 3D→정면깊이, 없으면 CPU relief 폴백
    from ai.varco import available as varco_on
    print(f"[등록] 2/3 형태 H 생성 — {'VARCO image-to-3D (1~2분)' if (type!='2d' and varco_on()) else 'CPU relief'}", flush=True)
    try:
        from ai.varco import image_to_3d_to_file
        if type != "2d" and varco_on():
            from pipeline.mesh import glb_to_h
            glb = _DATA / f"{aid}.glb"
            image_to_3d_to_file(str(clean_png), str(glb))   # ~1~2분
            H = glb_to_h(str(glb)); notes.append("VARCO image-to-3D")
        else:
            H = image_to_h(str(clean_png if cut else dst), art_type=type)
            notes.append("CPU relief (VARCO 미연동)" if type != "2d" else "윤곽 relief")
    except Exception as e:
        print(f"[등록]     3D 실패 → relief 폴백: {e}", flush=True)
        H = image_to_h(str(dst), art_type=type); notes.append(f"3D 실패→relief")
    _H_CACHE[aid] = H.astype(int).flatten().tolist()
    print(f"[등록]     H 완료 — 솟은 핀 {(H>0).sum()}/{H.size}", flush=True)

    if reuse:
        existing.update({"era": era or existing.get("era", ""), "type": type})
        art = existing
    else:
        art = {"id": aid, "title": title, "era": era, "type": type, "material": ""}
        ARTWORKS.append(art); _BY_ID[aid] = art

    # 3) 제목으로 외부 데이터(위키) 자동 수집 + 재인덱싱 (이미 있으면 건너뜀)
    print("[등록] 3/3 위키 자동수집 + RAG 인덱싱…", flush=True)
    try:
        from rag.fetch_wiki import save as wiki_save
        from rag.store import ingest as rag_ingest
        got = wiki_save(aid, [title]) if title else 0
        rag_ingest()
        notes.append(f"위키 {got}건 자동수집·인덱싱")
    except Exception as e:
        notes.append(f"RAG 수집 건너뜀({e})")
    _db.upsert(art, h=_H_CACHE.get(aid))     # 영속 저장(재시작해도 유지)
    print(f"[등록] ✅ 완료 — {aid} | {' / '.join(notes)}\n", flush=True)

    return {**{k: art[k] for k in ("id", "title", "era", "type")}, "notes": notes}


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
    _db.delete(artwork_id)                     # DB 에서도 제거
    return {"deleted": artwork_id}


@app.get("/api/artworks/{artwork_id}/heightmap")
def heightmap(artwork_id: str):
    art = _BY_ID.get(artwork_id)
    if not art:
        raise HTTPException(404, "unknown artwork")
    import numpy as np
    if artwork_id in _H_CACHE:                      # 업로드 작품: 사진/3D 에서 만든 H
        H = np.array(_H_CACHE[artwork_id], dtype=np.int16).reshape(C.GRID_ROWS, C.GRID_COLS)
    else:
        # 데모/카탈로그에 실제 사진 파일(data/artworks/<id>.png|jpg)이 있으면 그걸로 H 생성
        imgs = list(_DATA.glob(f"{artwork_id}.png")) + list(_DATA.glob(f"{artwork_id}.jpg")) \
            + list(_DATA.glob(f"{artwork_id}.jpeg"))
        if imgs:
            H = image_to_h(str(imgs[0]), art_type=art.get("type", "3d"))
            _H_CACHE[artwork_id] = H.astype(int).flatten().tolist()
            _db.upsert(art, h=_H_CACHE[artwork_id])     # 데모에 실제 사진 넣은 경우도 저장
        else:                                       # 실제 사진 없음 → 합성 예시(placeholder)
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
            _db.upsert(art, docent=_DOCENT_CACHE[artwork_id])   # 도슨트 캐시 영속(없으면 삽입)
        except Exception as e:
            raise HTTPException(502, f"EXAONE 호출 실패: {e}")
    return {"artwork_id": artwork_id, **_DOCENT_CACHE[artwork_id]}


@app.get("/api/artworks/{artwork_id}/ambience")
def ambience(artwork_id: str):
    """VARCO text2sound → 작품 분위기음/효과음 WAV (낭독 아님, ≤10초)."""
    from fastapi.responses import FileResponse, JSONResponse
    art = _BY_ID.get(artwork_id)
    if not art:
        raise HTTPException(404, "unknown artwork")
    cache = Path(__file__).resolve().parent.parent / "audio_cache"
    cache.mkdir(exist_ok=True)
    wav = cache / f"{artwork_id}_ambience.wav"
    if not wav.exists():
        prompt = art.get("ambience") or f"{art['title']}이(가) 놓인 고요한 전시실의 잔잔한 분위기 소리"
        try:
            from ai.varco import text2sound_to_file
            text2sound_to_file(prompt, str(wav))
        except Exception as e:
            return JSONResponse({"error": f"VARCO text2sound 미연동/실패: {e}"}, status_code=503)
    return FileResponse(str(wav), media_type="audio/wav")


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
