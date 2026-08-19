"""프로젝트 전역 설정.

경로, 하이퍼파라미터, 사용할 모델 이름 등을 이 파일에서 관리합니다.
클래스(피부 상태) 이름은 하드코딩하지 않고, 학습 시 data/train 폴더 구조에서
자동으로 추출해 checkpoints/class_names.json 에 저장 -> 추론 시 그대로 로드합니다.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # .env 파일에서 OPENAI_API_KEY 등을 읽어옴

# ---- 경로 설정 ----
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"                       # data/train/<class>/*.jpg, data/val/<class>/*.jpg
CHECKPOINT_DIR = BASE_DIR / "checkpoints"
CHECKPOINT_PATH = CHECKPOINT_DIR / "cnn_best.pt"
CLASS_NAMES_PATH = CHECKPOINT_DIR / "class_names.json"

# ---- CNN(1차 이미지 분류) 설정 ----
CNN_BACKBONE = "efficientnet_b0"   # "efficientnet_b0" 또는 "resnet50"
IMAGE_SIZE = 224
BATCH_SIZE = 32
EPOCHS = 15
LEARNING_RATE = 1e-4

# ---- LLM(2차 종합 분석) 설정 ----
# OpenAI GPT API 사용. https://platform.openai.com/api-keys 에서 발급 (유료, 카드 등록 필요).
LLM_MODEL = "gpt-4o-mini"  # 빠르고 저렴한 모델. 구조화 출력(response_format) 지원 필요
LLM_API_KEY_ENV = "OPENAI_API_KEY"
