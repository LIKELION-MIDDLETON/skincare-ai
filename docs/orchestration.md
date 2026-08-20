# 피부 분석 + 추천 오케스트레이션 설계 (논의 중)

> 상태: 논의 중 (미확정). PR #4(`feat/skin-analysis-model`, `model/` 디렉터리)와
> 기존 추천 API(`main.py`, `ml_engine.py`)를 백엔드가 어떻게 엮을지에 대한 검토 기록.

## 배경

- `model/`: CNN(1차 이미지 분류) + LLM(2차 종합 분석) 파이프라인. `SkinAnalysisPipeline.run(image, answers)`가
  `{"cnn_result", "llm_result", "survey"}` 형태의 dict를 반환.
- 루트 `main.py`: `/recommend` 엔드포인트. `Req` 스키마(`cnn_result`, `llm_result`, `survey`)가
  `model/`의 출력 형태와 필드명까지 정확히 일치하도록 이미 맞춰져 있음.
- 클래스 라벨(`model/checkpoints/class_names.json`)과 `main.py`의 `CLASSES` 리스트도 순서까지 동일.
- 즉 **인터페이스 설계 자체는 이미 정합적**이고, 남은 것은 두 모듈을 어떻게 배치/연결할지의 문제.

## 검토한 옵션

### 옵션 A. 같은 프로세스 내 임포트 (모노레포, 단일 서비스)

`model/`을 정식 파이썬 패키지로 리팩터링해서 `main.py`가 직접 `SkinAnalysisPipeline`을 import.

```python
from model.pipeline import SkinAnalysisPipeline
pipeline = SkinAnalysisPipeline()  # 기동 시 1회 로드

@app.post("/analyze-and-recommend")
def full_flow(image, answers):
    r = pipeline.run(image, answers)
    return recommend(Req(**r))
```

**장점**
- 배포 파이프라인 1개, Dockerfile 1개로 끝남. 팀 규모 대비 운영 부담이 가장 적음.
- 네트워크 홉이 없어 구현이 단순함.

**단점 / 선결 과제**
- `model/*.py`가 전부 `import config`, `from cnn_infer import ...` 같은 **플랫(flat) 임포트** 스타일이라
  패키지로 바로 못 씀. `model/__init__.py` 추가 + 상대 임포트(`from . import config`)로 리팩터링 필요.
- 루트 `requirements.txt`(fastapi, uvicorn, pydantic)와 `model/requirements.txt`(torch, torchvision,
  opencv 등)를 통합해야 함 → 이미지가 무거워짐(아래 옵션 B의 용량 분석 참고).
- 현재 `Dockerfile`은 루트 `requirements.txt`만 설치하도록 되어 있어 그대로면 `model/` import 시
  `ModuleNotFoundError` 발생 — 반드시 고쳐야 함.
- `checkpoints/cnn_best.pt`(학습 가중치)가 저장소에 없음 — 포함할지 외부 스토리지에서 받을지 결정 필요.

### 옵션 B. 마이크로서비스로 분리 (model-service 별도 배포)

`model/`을 독립 FastAPI 서비스(자체 Dockerfile)로 띄우고, 루트 `main.py`가 HTTP로 호출.

```
사용자 업로드 → 백엔드가 S3 업로드 (presigned PUT 또는 백엔드 경유 업로드)
→ 백엔드가 model-service 호출: POST /analyze { image_url: <S3 presigned GET>, answers: {...} }
→ model-service: S3에서 이미지 다운로드 → CNN 추론 → LLM 2차 분석 → JSON 응답 (동기)
→ 백엔드가 그 결과를 그대로 /recommend 에 전달
```

**Docker 이미지 용량 검토 (CPU 전용 기준)**

| 구성요소 | 용량 |
|---|---|
| `python:3.11-slim` | ~150MB |
| `torch` (CPU wheel) | ~200MB |
| `torchvision` | ~30MB |
| `opencv-python-headless` | ~90MB |
| 기타(pillow, numpy, openai, dotenv) | ~50MB |
| **합계** | **약 700MB~1GB** |

⚠️ `requirements.txt`에 `torch>=2.1.0`만 쓰면 pip가 기본 CUDA 포함 wheel을 받아 이미지가 3~4GB로 커짐.
GPU 없는 서버라면 반드시 CPU 전용 인덱스로 설치:
```dockerfile
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

**지연시간(latency) 검토**

전체 체인의 병목은 아키텍처 분리가 아니라 **LLM API 호출(초 단위)**:

| 단계 | 예상 소요 |
|---|---|
| 백엔드 → S3 업로드 | ~200-500ms |
| model-service → S3 다운로드 | ~100-300ms |
| CNN 추론(EfficientNet-B0, CPU, 1장) | ~50-200ms |
| LLM(GPT) 2차 분석 호출 | ~1-3초 (경우에 따라 더 길어질 수 있음) |

서비스를 나눠서 생기는 추가 오버헤드(네트워크 홉 1회 + S3 왕복)는 수백 ms 수준이라, 이미 초 단위인
LLM 호출 대비 무시할 만한 수준. **분리 자체가 체감 속도를 크게 늦추진 않음.**

**장점**
- 무거운 torch 의존성이 가벼운 추천 API와 분리되어 배포/스케일링이 깔끔해짐.
- `GEMINI_API_KEY`(현재는 `OPENAI_API_KEY`) 같은 시크릿이 model-service에만 존재 — 시크릿 격리 면에서 유리.
- `model/`의 파일 배치를 거의 그대로 활용 가능(FastAPI 래퍼만 추가).

**단점 / 선결 과제**
- 서비스 2개 운영 → 배포 파이프라인 2개, 헬스체크 2개, 장애 지점 1개 추가.
- model-service가 S3(다운로드용)와 LLM API(외부 인터넷) 둘 다에 네트워크 egress가 있어야 함.
  private subnet 배치 시 NAT/VPC 엔드포인트 구성 필요.
- 백엔드 → model-service 호출의 타임아웃을 넉넉히(20~30초) 잡아야 함.
- `SkinCNNPredictor`/`SkinLLMAnalyzer`를 요청마다 새로 만들지 말고 서비스 기동 시 1회만 로드해서
  재사용하도록 구현해야 함(그렇지 않으면 매 요청마다 checkpoint 재로드로 느려짐).
- 로컬 파일 경로 기반인 `cnn_infer.predict()`를 S3 URL 다운로드 어댑터로 감싸는 코드 추가 필요.

### 옵션 C. 우선 현재 구조로 진행, 추후 정리

지금은 `model/`과 루트가 파일만 나란히 존재하는 상태(연결 코드 없음)로 두고, 실제 연동/리팩터링은
추후 스프린트에서 진행. 리뷰만 기록해두고 결정은 보류.

## 현재 상태

- **LLM 프로바이더는 Gemini → OpenAI GPT(`gpt-4o-mini`)로 교체 완료** (`model/llm_analyzer.py`,
  `model/config.py`, `model/.env.example`, `model/requirements.txt`, `model/README.md` 반영).
  - Gemini는 무료 티어가 있었으나 OpenAI는 결제 수단 등록 및 종량 과금이 필요 — 트래픽 대비 사용량 한도
    설정을 권장.
- 오케스트레이션 방식(옵션 A/B/C)은 **아직 최종 확정되지 않음**. 마이크로서비스(B) 방향으로 기울고 있으나,
  팀 인원/일정을 고려해 최종 결정 필요.
- 이 미확정 상태와 별개로, 루트 `/recommend`에도 **자체 OpenAI 연동을 추가**했다(추천 이유 생성,
  `graph_reasons.py`+`llm_reasons.py`, 상세는 `docs/추천이유_그래프_LLM.md`). 즉 지금은 `model/`과
  루트 양쪽에 각자 `OPENAI_API_KEY`·`openai` 의존성이 따로 있다. 옵션 A(같은 프로세스로 합치기)로
  가게 되면 이 두 OpenAI 클라이언트 초기화도 함께 정리해야 한다.

## 공통으로 필요한 선결 작업 (옵션 무관)

1. ~~`checkpoints/cnn_best.pt` 확보 방안 결정 (레포 포함 vs 외부 스토리지 다운로드)~~ →
   **결정: 레포/이미지에는 안 넣음.** 배포 서버의 `model/checkpoints/cnn_best.pt` 경로에 파일을
   직접 옮겨두고(Drive/scp 등, git 아님), `docker-compose.yml`에서 volume으로 컨테이너에 마운트.
   모델 갱신 시 이미지 재빌드 없이 파일만 교체하면 됨.
2. `model/` 내부 임포트 스타일 정리(플랫 임포트 → 패키지 임포트 또는 서비스 진입점 명확화)
3. CNN `top_k`를 클래스 전체 개수(8개)로 반환하도록 맞추기 — `main.py`의 `to_probs()`가 일부만 오면
   나머지를 균등 분배하는데, 이는 `medical` 합산 임계값 판단을 왜곡할 수 있음
4. `need_professional_care` 등 의료 권고 플래그 연동 테스트
