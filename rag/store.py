"""
A2 RAG — Chroma 벡터 스토어 (인덱싱 + 검색).

지금은 chromadb 기본 임베딩(onnx MiniLM)을 쓴다 — 무거운 torch 없이 CPU로 동작.
검색은 항상 artwork_id 로 스코프하므로(선택된 유물 안에서만) 임베딩 품질 의존도가 낮다.

  TODO(B3): 임베딩을 BGE-Korean / KoSimCSE 로 교체(GPU 서빙) → 한국어 검색 품질↑
  TODO(A2): 코퍼스를 e뮤지엄 메타·학술자료로 확장, 청킹/스키마 정교화

사용:
  python -m rag.store ingest      # corpus/*.json → Chroma 인덱싱
  python -m rag.store query buddha_01 "왜 손을 뺨에 댔어?"
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import chromadb

_DIR = Path(__file__).resolve().parent
_CHROMA = _DIR.parent / "chroma"
_CORPUS = _DIR / "corpus"
_COLL = "artworks"


def _client():
    return chromadb.PersistentClient(path=str(_CHROMA))


def _chunk(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    """문단 우선 → 길면 size 단위로 분할(약간 겹치게). 학술자료/위키 본문용."""
    paras = [p.strip() for p in text.replace("\r", "").split("\n\n") if p.strip()]
    out: list[str] = []
    for p in paras:
        if len(p) <= size:
            out.append(p)
        else:
            i = 0
            while i < len(p):
                out.append(p[i:i + size])
                i += size - overlap
    return out


def ingest() -> int:
    """
    (재)인덱싱:
      1) corpus/*.json        — 손수 큐레이션한 핵심 사실 청크
      2) corpus/docs/<id>/*.txt|*.md — 위키/학술자료 등 외부 문서(자동 청킹)
    둘 다 metadata.artwork_id 로 묶여, 검색은 선택된 유물 안에서만 수행된다.
    """
    client = _client()
    try:
        client.delete_collection(_COLL)
    except Exception:
        pass
    coll = client.create_collection(_COLL)
    ids, docs, metas = [], [], []

    # 1) 큐레이션 JSON
    for f in sorted(_CORPUS.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        aid = d["artwork_id"]
        for i, ch in enumerate(d["chunks"]):
            ids.append(f"{aid}#json#{i}")
            docs.append(ch["text"])
            metas.append({"artwork_id": aid, "title": d.get("title", ""),
                          "source": ch.get("source", "")})

    # 2) 외부 문서 (corpus/docs/<artwork_id>/*.txt|*.md)
    docs_root = _CORPUS / "docs"
    for adir in sorted(docs_root.glob("*")) if docs_root.exists() else []:
        if not adir.is_dir() or adir.name.startswith("_"):   # _cache 등 내부 폴더 제외
            continue
        aid = adir.name
        for f in sorted(list(adir.glob("*.txt")) + list(adir.glob("*.md"))):
            src = f.stem
            for i, ch in enumerate(_chunk(f.read_text(encoding="utf-8"))):
                ids.append(f"{aid}#doc#{src}#{i}")
                docs.append(ch)
                metas.append({"artwork_id": aid, "title": aid, "source": src})

    if ids:
        coll.add(ids=ids, documents=docs, metadatas=metas)
    return len(ids)


def retrieve(artwork_id: str, query: str, k: int = 4) -> list[dict]:
    """선택된 유물 안에서만 query 와 가까운 청크 top-k. [{text, source}]."""
    try:
        coll = _client().get_collection(_COLL)
    except Exception:
        return []   # 아직 인덱싱 안 됨 → 컨텍스트 없이 진행
    res = coll.query(query_texts=[query], n_results=k,
                     where={"artwork_id": artwork_id})
    out = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    for doc, meta in zip(docs, metas):
        out.append({"text": doc, "source": meta.get("source", "")})
    return out


def context_for(artwork_id: str, query: str, k: int = 4) -> tuple[str, list[str]]:
    """LLM 프롬프트에 주입할 컨텍스트 문자열 + 출처 목록."""
    hits = retrieve(artwork_id, query, k)
    if not hits:
        return "", []
    ctx = "\n".join(f"- ({h['source']}) {h['text']}" for h in hits)
    sources = list(dict.fromkeys(h["source"] for h in hits if h["source"]))
    return ctx, sources


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "ingest":
        print("indexed chunks:", ingest())
    elif len(sys.argv) >= 3 and sys.argv[1] == "query":
        for h in retrieve(sys.argv[2], " ".join(sys.argv[3:]) or "도슨트"):
            print(f"[{h['source']}] {h['text'][:80]}…")
    else:
        print(__doc__)
