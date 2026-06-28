# ai/ — A1 AI 파이프라인 (담당: 박찬영 / 방수윤)

API 호출 래퍼. 키는 `.env` 에서 로드(`python-dotenv`). 절대 커밋 금지.

| 모듈(예정) | 역할 | API | 호출 시점 |
|---|---|---|---|
| `tts.py` | 도슨트 낭독·분위기음·효과음·"분석 중" 필러 | VARCO **text2sound** | 사전 캐싱 + 실시간 |
| `docent.py` | 작품 메타 + RAG 컨텍스트 → 도슨트 텍스트 | **EXAONE** | 등록 시 |
| `qa.py` | 후속 질문 → 답변 → tts | **EXAONE** + RAG | 실시간 |
| `saliency.py` | VLM 시맨틱 중요부위 마킹(relief 강조/안내) | **EXAONE VLM** | 등록 시 |
| `image_to_3d.py` | 다각도 사진 → mesh (국내 AI 트랙 어필, 선택) | VARCO **image-to-3D** | 등록 시 1회 |

> 모든 H 출력은 `pipeline/contract.py` 포맷을 따른다. 오디오는 `audio_cache/`(gitignore).
