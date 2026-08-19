"""raw_data/의 원본 이미지를 data/train, data/val (ImageFolder 규격)로 정리한다.

두 소스(DermNet: 스튜디오 임상사진 / normal_source: 폰카 셀카)의 촬영 환경 차이로
모델이 "질환 vs 정상"이 아니라 "촬영 스타일"을 학습해버리는 도메인 갭 문제를 줄이기 위해,
모든 이미지에 동일한 조명 정규화(CLAHE)를 적용한 뒤 저장한다.

실행:
    python prepare_data.py
"""

import random
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import config

RAW_DIR = config.BASE_DIR / "raw_data"
DERMNET_DIR = RAW_DIR / "dermnet"
NORMAL_SOURCE_DIR = RAW_DIR / "normal_source" / "normal"

RANDOM_SEED = 42
NORMAL_VAL_RATIO = 0.2

# DermNet 원본 폴더명 -> 프로젝트에서 쓸 클래스 슬러그
DERMNET_CLASS_MAP = {
    "Acne and Rosacea Photos": "acne_rosacea",
    "Atopic Dermatitis Photos": "atopic_dermatitis",
    "Eczema Photos": "eczema",
    "Psoriasis pictures Lichen Planus and related diseases": "psoriasis_lichen_planus",
    "Light Diseases and Disorders of Pigmentation": "pigmentation_disorder",
    "Urticaria Hives": "urticaria",
    "Tinea Ringworm Candidiasis and other Fungal Infections": "fungal_infection",
}
NORMAL_CLASS_NAME = "normal"


def normalize_lighting(image: Image.Image) -> Image.Image:
    """LAB 색공간의 L채널에 CLAHE를 적용해 스튜디오 조명/폰카 플래시 간 밝기·대비 차이를 줄인다."""
    arr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(arr)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    arr = cv2.merge((l, a, b))
    rgb = cv2.cvtColor(arr, cv2.COLOR_LAB2RGB)
    return Image.fromarray(rgb)


def process_and_save(src_path: Path, dst_path: Path) -> bool:
    try:
        image = Image.open(src_path)
        image = normalize_lighting(image)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(dst_path.with_suffix(".jpg"), "JPEG", quality=92)
        return True
    except Exception as exc:  # 손상된 이미지 등은 건너뛴다
        print(f"  [건너뜀] {src_path.name}: {exc}")
        return False


def build_dermnet_classes():
    for dermnet_name, slug in DERMNET_CLASS_MAP.items():
        for split, src_root in (("train", DERMNET_DIR / "train"), ("val", DERMNET_DIR / "test")):
            src_dir = src_root / dermnet_name
            files = sorted(src_dir.glob("*"))
            ok = 0
            for f in files:
                if process_and_save(f, config.DATA_DIR / split / slug / f.stem):
                    ok += 1
            print(f"[{slug}] {split}: {ok}/{len(files)}")


def build_normal_class():
    files = sorted(NORMAL_SOURCE_DIR.glob("*"))
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(files)

    n_val = max(1, int(len(files) * NORMAL_VAL_RATIO))
    val_files, train_files = files[:n_val], files[n_val:]

    for split, split_files in (("train", train_files), ("val", val_files)):
        ok = 0
        for f in split_files:
            if process_and_save(f, config.DATA_DIR / split / NORMAL_CLASS_NAME / f.stem):
                ok += 1
        print(f"[{NORMAL_CLASS_NAME}] {split}: {ok}/{len(split_files)}")


if __name__ == "__main__":
    if not DERMNET_DIR.exists():
        raise FileNotFoundError(f"{DERMNET_DIR} 없음. raw_data/dermnet에 DermNet 압축을 풀어두세요.")
    if not NORMAL_SOURCE_DIR.exists():
        raise FileNotFoundError(f"{NORMAL_SOURCE_DIR} 없음.")

    build_dermnet_classes()
    build_normal_class()

    print("\n=== 최종 클래스별 이미지 수 ===")
    for split in ("train", "val"):
        print(f"-- {split} --")
        split_dir = config.DATA_DIR / split
        for class_dir in sorted(split_dir.iterdir()):
            if class_dir.is_dir():
                count = len(list(class_dir.glob("*.jpg")))
                print(f"  {class_dir.name}: {count}")
