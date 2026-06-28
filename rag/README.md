# rag/ — A2 RAG (담당: 박찬영 / 방수윤)

작품별 사실 정확성 확보. Chroma + BGE-Korean.

| 모듈(예정) | 역할 |
|---|---|
| `ingest.py` | 코퍼스 수집·전처리·청킹 (e뮤지엄·도자사·불교조각사·접근성 도슨트) |
| `embed.py` | BGE-Korean / KoSimCSE 임베딩 → Chroma 인덱싱 |
| `retrieve.py` | 질의 → top-k 검색 → 프롬프트 주입 |
| `eval.py` | 환각/정확도 평가셋 |

Chroma DB(`chroma/`)와 코퍼스 원본은 gitignore. 스키마/청킹 규칙만 커밋.
