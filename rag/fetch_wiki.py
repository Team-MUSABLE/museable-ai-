"""
A2 — 한국어 위키백과 본문 수집 (공개 API, 키 불필요).

작품/주제명을 주면 위키백과 본문을 받아 corpus/docs/<artwork_id>/wiki_<제목>.txt 로 저장.
저장 후 `python -m rag.store ingest` 하면 인덱싱된다.

사용:
  python -m rag.fetch_wiki buddha_01 "금동반가사유상" "반가사유상"
  python -m rag.fetch_wiki celadon_01 "청자 상감운학문 매병" "고려청자" "상감기법"
  python -m rag.fetch_wiki ssireum_01 "씨름 (김홍도)" "김홍도"

학술 PDF/문서를 직접 넣으려면: 텍스트로 변환해 같은 폴더에 .txt/.md 로 두면 끝.
(저작권 확인 필수 — 공공누리/공개 라이선스 자료만.)
"""
from __future__ import annotations
import sys
from pathlib import Path
import requests

_DOCS = Path(__file__).resolve().parent / "corpus" / "docs"
_API = "https://ko.wikipedia.org/w/api.php"


def fetch_extract(title: str) -> str | None:
    """위키백과 문서 평문 본문 추출 (없으면 None)."""
    r = requests.get(_API, params={
        "action": "query", "prop": "extracts", "explaintext": 1,
        "redirects": 1, "format": "json", "titles": title,
    }, headers={"User-Agent": "museable-rag/0.1 (research demo)"}, timeout=30)
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", {})
    for _, p in pages.items():
        if "extract" in p and p["extract"].strip():
            return p["extract"]
    return None


def fetch_main_image(title: str) -> bytes | None:
    """위키백과 문서 대표 이미지(원본) 다운로드. 없으면 None."""
    r = requests.get(_API, params={
        "action": "query", "prop": "pageimages", "piprop": "original",
        "redirects": 1, "format": "json", "titles": title,
    }, headers={"User-Agent": "museable-rag/0.1 (research demo)"}, timeout=30)
    r.raise_for_status()
    for _, p in r.json().get("query", {}).get("pages", {}).items():
        url = (p.get("original") or {}).get("source")
        if url:
            img = requests.get(url, headers={"User-Agent": "museable-rag/0.1"}, timeout=60)
            if img.ok:
                return img.content
    return None


def save(artwork_id: str, titles: list[str]) -> int:
    out_dir = _DOCS / artwork_id
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = _DOCS / "_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for t in titles:
        safe = t.replace("/", "_").replace(" ", "_")
        fn = out_dir / f"wiki_{safe}.txt"
        if fn.exists() and fn.stat().st_size > 0:          # 이미 있으면 다시 저장 안 함
            print(f"  [skip] '{t}' 이미 있음 — 재저장 안 함")
            continue
        cache = cache_dir / f"{safe}.txt"
        if cache.exists() and cache.stat().st_size > 0:    # 같은 제목 캐시 재사용(재다운로드 X)
            content = cache.read_text(encoding="utf-8")
            print(f"  [cache] '{t}' 캐시 재사용")
        else:
            text = fetch_extract(t)
            if not text:
                print(f"  [skip] '{t}' 문서 없음")
                continue
            content = f"# 출처: 위키백과 「{t}」\n\n{text}"
            cache.write_text(content, encoding="utf-8")
            print(f"  [ok] {t} 다운로드 ({len(text)}자)")
        fn.write_text(content, encoding="utf-8")
        n += 1
    return n


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(0)
    aid, titles = sys.argv[1], sys.argv[2:]
    print(f"[{aid}] 위키백과 수집:")
    got = save(aid, titles)
    print(f"완료: {got}개 문서. 이제 `python -m rag.store ingest` 실행.")
