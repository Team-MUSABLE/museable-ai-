"""
A5 — 영속 저장(SQLite). 등록 작품 카탈로그 + H 캐시 + 도슨트 캐시를 저장해
서버 재시작/리로드 후에도 유지한다. 가볍게(표준 sqlite3) 구현.

DB 파일: museable.db (gitignore 권장)
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

_DB = Path(__file__).resolve().parent.parent / "museable.db"


def _conn():
    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS artworks (
                id TEXT PRIMARY KEY,
                title TEXT, era TEXT, type TEXT, material TEXT,
                ambience TEXT,
                h_json TEXT,          -- 핀 H(정수 배열) JSON, 없으면 NULL
                docent TEXT,          -- 캐시된 도슨트 JSON, 없으면 NULL
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)


def upsert(art: dict, h: list | None = None, docent: dict | None = None):
    """작품 저장/갱신. h/docent 는 주어진 것만 갱신(None이면 기존 유지)."""
    with _conn() as c:
        row = c.execute("SELECT h_json, docent FROM artworks WHERE id=?", (art["id"],)).fetchone()
        h_json = json.dumps(h) if h is not None else (row["h_json"] if row else None)
        doc = json.dumps(docent, ensure_ascii=False) if docent is not None else (row["docent"] if row else None)
        c.execute("""
            INSERT INTO artworks (id,title,era,type,material,ambience,h_json,docent)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, era=excluded.era, type=excluded.type,
                material=excluded.material, ambience=excluded.ambience,
                h_json=excluded.h_json, docent=excluded.docent
        """, (art["id"], art.get("title", ""), art.get("era", ""), art.get("type", "3d"),
              art.get("material", ""), art.get("ambience", ""), h_json, doc))


def set_h(aid: str, h: list):
    with _conn() as c:
        c.execute("UPDATE artworks SET h_json=? WHERE id=?", (json.dumps(h), aid))


def set_docent(aid: str, docent: dict):
    with _conn() as c:
        c.execute("UPDATE artworks SET docent=? WHERE id=?",
                  (json.dumps(docent, ensure_ascii=False), aid))


def delete(aid: str):
    with _conn() as c:
        c.execute("DELETE FROM artworks WHERE id=?", (aid,))


def load_all() -> list[dict]:
    """저장된 모든 작품 → [{art..., _h, _docent}]."""
    with _conn() as c:
        rows = c.execute("SELECT * FROM artworks ORDER BY created_at").fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "title": r["title"], "era": r["era"], "type": r["type"],
            "material": r["material"] or "", "ambience": r["ambience"] or "",
            "_h": json.loads(r["h_json"]) if r["h_json"] else None,
            "_docent": json.loads(r["docent"]) if r["docent"] else None,
        })
    return out
