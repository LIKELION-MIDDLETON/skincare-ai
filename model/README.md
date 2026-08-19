# 피부 상태 분석 모델 (이미지 CNN + 텍스트 LLM 2단계 파이프라인)

담당 파트: 이미지를 CNN으로 1차 분류 -> 설문 응답 + CNN 결과를 LLM API(OpenAI GPT)에 넣어 2차 종합 분석.

## 폴더 구조

```
skin_analysis/
  config.py          # 경로/하이퍼파라미터/모델명 설정
  cnn_model.py        # 전이학습 CNN 정의 (efficientnet_b0 / resnet50)
  train_cnn.py         # CNN 학습 스크립트
  cnn_infer.py          # 학습된 CNN으로 1차 추론
  survey.py              # 사용자 입력용 정해진 설문 문항 정의 + 답변 -> 텍스트 변환
  llm_analyzer.py         # 텍스트 + CNN 결과 -> OpenAI GPT API 2차 분석
  pipeline.py               # 전체 파이프라인 (CNN -> LLM) 실행 진입점
  requirements.txt
  .env.example
  data/
    train/<클래스명>/*.jpg     # 클래스에 "Normal"(정상)도 포함시킬 것
    val/<클래스명>/*.jpg
  checkpoints/
    cnn_best.pt          # 학습 후 생성됨
    class_names.json      # 학습 후 생성됨 (클래스 목록)
```

## 1. 환경 설정

```bash
cd skin_analysis
pip install -r requirements.txt
cp .env.example .env
```

`.env` 파일을 열어 `OPENAI_API_KEY`에 키를 넣습니다. https://platform.openai.com/api-keys 에서
발급받습니다. Gemini와 달리 무료 티어가 없고 결제 수단 등록 및 사용량 과금이 필요하니,
트래픽 규모에 맞춰 사용량 한도(usage limit)를 미리 설정해두는 것을 권장합니다.

## 2. 학습 데이터 준비

`data/train/<클래스명>/이미지들`, `data/val/<클래스명>/이미지들` 형태(torchvision ImageFolder 규격)로
이미지를 정리합니다. 클래스명은 폴더 이름 그대로 자동 인식되므로 하드코딩할 필요 없습니다.
**"정상(Normal)" 피부/얼굴 이미지도 반드시 하나의 클래스 폴더로 포함시켜야** CNN이 "이상 없음"도 예측할 수 있습니다.

### 무료 공개 데이터셋 후보

- **Skin Disease and Normal Skin Dataset (Kaggle, 추천)** — 여드름 등 피부질환 이미지 + **정상 피부(Normal) 이미지**가
  함께 들어있어 지금 프로젝트 목적(질환 여부 + 정상 판별)에 바로 맞음.
  https://www.kaggle.com/datasets/lysaapriani/skin-disease-and-normal-skin-dataset

- **DermNet (Kaggle)** — 여드름, 습진, 건선, 아토피피부염 등 23개 피부질환 카테고리, 이미 train/test로
  분할되어 제공됨. 다만 "정상" 클래스가 없으므로 위 데이터셋의 Normal 이미지를 `data/train/Normal`,
  `data/val/Normal` 폴더에 함께 넣어서 보완하는 것을 권장.
  https://www.kaggle.com/datasets/shubhamgoel27/dermnet

- **Facial Skin Condition Dataset (Kaggle)** — 얼굴 400명, 1,200여 장. 피부 톤/타입이 다양하고
  여드름·발진 등 세부 라벨이 있어 보조 데이터로 활용 가능.
  https://www.kaggle.com/datasets/unidpro/facial-skin-condition-dataset

Kaggle CLI로 받는 예시:
```bash
pip install kaggle --break-system-packages
# kaggle.json API 토큰을 ~/.kaggle/ 에 넣은 후
kaggle datasets download -d lysaapriani/skin-disease-and-normal-skin-dataset -p data_raw --unzip
```
받은 폴더 구조를 아래처럼 `data/train/<클래스>`, `data/val/<클래스>`로 정리해서 넣으면 됩니다.

예:
```
data/train/Acne/img001.jpg
data/train/Normal/img002.jpg
data/train/Atopic_Dermatitis/img003.jpg
data/val/Acne/img101.jpg
data/val/Normal/img102.jpg
...
```

## 3. CNN 학습

```bash
python train_cnn.py --data_dir data --epochs 15 --backbone efficientnet_b0
```

학습이 끝나면 `checkpoints/cnn_best.pt`(가중치)와 `checkpoints/class_names.json`(클래스 목록)이 저장됩니다.

## 4. 사용자 입력: 자유 텍스트 대신 정해진 설문

기존에는 사용자가 피부 상태를 자유 텍스트로 서술했지만, 지금은 `survey.py`에 정의된
공통 설문 문항에 답하는 방식으로 바뀌었습니다. 프론트/서버는 `survey.SURVEY_QUESTIONS`를
그대로 문항 정의(라디오/체크박스 UI 스펙)로 사용하면 됩니다.

| id | 질문 | 선택 방식 | 옵션 |
|---|---|---|---|
| `skin_type` | 피부 타입은 어떻게 되나요? | 단일 선택 | 건성 / 지성 / 복합성(T존 지성·볼 건성) / 수부지(속건조 지성) / 민감성 / 잘 모르겠음 |
| `main_concern` | 가장 신경 쓰이는 고민은 무엇인가요? | 복수 선택 | 여드름/뾰루지, 블랙헤드/모공, 홍조/붉은기, 건조함/각질, 색소침착/기미, 주름/탄력저하, 가려움/따가움, 특별한 고민 없음 |
| `duration` | 위 고민은 얼마나 지속되었나요? | 단일 선택 | 해당 없음 / 1주 이내 / 1~4주 / 1~3개월 / 3개월 이상 |
| `location` | 주로 어느 부위에 나타나나요? | 복수 선택 | 이마, 코(T존), 볼, 턱, 눈가, 얼굴 전체, 해당 없음 |
| `sensitivity` | 새 화장품 사용 시 트러블이 잘 생기나요? | 단일 선택 | 전혀 그렇지 않다 / 가끔 그렇다 / 자주 그렇다 |
| `history` | 피부 질환으로 진단받은 적이 있나요? | 단일 선택 (`기타` 선택 시 `etc_note`로 자유 텍스트 추가) | 없음 / 아토피피부염 / 여드름(중증) / 지루성피부염 / 건선 / 기타(직접 입력) |

답변은 아래와 같은 dict 형태로 모아 `pipeline.run()`에 넘기면, 내부적으로
`survey.answers_to_text()`가 LLM 프롬프트용 텍스트로 변환합니다.

```python
answers = {
    "skin_type": "지성",
    "main_concern": ["여드름/뾰루지", "블랙헤드/모공"],
    "duration": "1~4주",
    "location": ["볼", "코(T존)"],
    "sensitivity": "가끔 그렇다",
    "history": "없음",
}
```

## 5. 전체 파이프라인 실행 (이미지 + 설문 응답 -> 최종 결과)

```bash
python pipeline.py --image sample.jpg --answers '{"skin_type": "지성", "main_concern": ["여드름/뾰루지"], "duration": "1~4주"}'
```

콘솔에서 문항별로 하나씩 답하며 테스트하고 싶다면:

```bash
python interactive_test.py
```

출력은 다음 JSON 형태입니다.

```json
{
  "cnn_result": {
    "predicted_label": "Acne",
    "confidence": 0.87,
    "top_k": [{"label": "Acne", "confidence": 0.87}, {"label": "Normal", "confidence": 0.08}]
  },
  "llm_result": {
    "summary": "...",
    "likely_conditions": ["..."],
    "reasoning": "...",
    "care_recommendations": ["..."],
    "need_professional_care": true,
    "disclaimer": "..."
  }
}
```

CNN이 "Normal"을 예측하고 설문 응답에도 특이사항이 없으면, LLM이 안심시켜주는 톤으로
`need_professional_care: false`인 결과를 생성하도록 프롬프트에 반영되어 있습니다.

## 다른 파트와 연동 시

`SkinAnalysisPipeline` 클래스(`pipeline.py`)를 그대로 import해서 쓰면 됩니다.

```python
from pipeline import SkinAnalysisPipeline

pipeline = SkinAnalysisPipeline()
result = pipeline.run(image_path="uploaded.jpg", survey_answers={"skin_type": "지성", ...})
```

FastAPI 등 서버 파트를 다른 팀원이 맡는다면, 위 `run()` 호출부만 엔드포인트에 연결하고
프론트에서 받은 설문 응답 JSON을 그대로 `survey_answers`에 넣으면 됩니다.
`pipeline.run()`은 `survey_answers`에 문자열(자유 텍스트)을 넘겨도 동작하도록 하위 호환을
남겨뒀지만, 신규 연동은 dict(설문 응답) 방식을 권장합니다.

## 참고

- CNN은 사전학습된 backbone(EfficientNet-B0 기본값)을 전이학습해 사용합니다. `config.py`의 `CNN_BACKBONE`을
  `resnet50`으로 바꾸면 ResNet50로도 학습할 수 있습니다.
- LLM은 OpenAI GPT API(`gpt-4o-mini`)를 사용합니다. `openai` SDK의 구조화 출력(`beta.chat.completions.parse`) +
  Pydantic 스키마로 항상 정해진 JSON 형식만 반환하도록 강제했습니다.
- LLM 결과는 의학적 진단이 아닌 참고 정보입니다. 실제 서비스에 배포 시 면책 문구 노출이 필요합니다.
