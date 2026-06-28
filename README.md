# museable — 가변형 핀 도슨트

> 시각장애인에게도, 박물관은 살아있다.
> 작품 사진을 AI가 **촉각 height map**으로 변환하고, 수백 개의 핀이 그 형태대로 솟아올라
> 손끝으로 작품을 직접 탐색하게 하는 시스템. 음성 도슨트·실시간 질의응답·점자 모드 포함.
>
> 2026 인공지능 루키 대회 · 국내 AI 트랙 · 팀 **뮤저블**

---

## 아키텍처 한눈에

```
작품 사진 ─▶ [A3] 정면 height map 파이프라인 ──▶ H (n×m, 0..15)
                depth/relief · ROI 리샘플 · 점자          │  ← 단일 계약(contract)
                                                          ▼
[A1] AI(VARCO text2sound / EXAONE+RAG) ◀──▶ [A5] FastAPI ──▶ [A4] 웹 3D 핀 뷰 (Three.js)
        음성 도슨트 · 실시간 Q&A                              핀이 H까지 실시간 상승
                                                          │
                                              (결선) ──────▶ FPGA: H → 이진수 직렬화 → 실제 핀 구동
```

**크리티컬 패스:** `A3(H 생성)` → `A4(핀 뷰)`. 그래서 **H 계약을 먼저 박았다.**
모든 컴포넌트는 [`docs/height-map-contract.md`](docs/height-map-contract.md) / [`pipeline/contract.py`](pipeline/contract.py)를 따른다.
웹 핀 높이값 = 결선 FPGA 이진수와 **동일 값** (결선에서 연결만 하면 됨).

## 폴더 구조

```
museable/
├─ docs/height-map-contract.md   # ★ H 계약 (단일 진실 공급원)
├─ pipeline/                     # A3 height map (CPU) — 크리티컬 패스 루트
│   ├─ contract.py               #   상수·검증·JSON·FPGA 직렬화
│   └─ relief.py                 #   depth→relief→H (지금은 합성 H, B1에서 실제 교체)
├─ backend/main.py               # A5 FastAPI — 작품/heightmap 서빙 + 웹 정적
├─ web/                          # A4 ★본선 메인 산출물 — Three.js 3D 핀 뷰
│   ├─ index.html
│   └─ main.js
├─ ai/   (README)                # A1 VARCO text2sound · EXAONE · image-to-3D
├─ rag/  (README)                # A2 Chroma + BGE-Korean
└─ data/artworks/                # A7 데모 작품 3점
```

## 지금 바로 돌려보기 (Phase A · CPU)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 백엔드 + 웹 (한 번에)
uvicorn backend.main:app --reload --port 8000
# → http://localhost:8000  에서 작품 선택 → 「핀 올리기」
```

백엔드 없이 웹만 보고 싶으면 `web/index.html` 을 정적 서버로 열면 된다
(JS 합성 H로 폴백 동작). 계약 자가점검: `python -m pipeline.contract`.

## 로드맵

- **Phase A (~7/10, GPU X):** A3 H 파이프라인 + A4 핀 뷰 끝단(선택→H→상승)을 CPU로 완성. A1/A2/A5 골격.
- **Phase B (7/10~8/14, GPU):** depth GPU 전환(B1), 핀 애니메이션·조명 폴리시(B2), E2E 루프(B4), 시연(B5).
- **결선(별도):** H → UART 직렬화 → FPGA 실제 핀 구동.

> 라이선스/데이터 출처: e뮤지엄(공공누리) 등 공개 자산 우선. 원본 이미지·모델 가중치는 git 미포함.
