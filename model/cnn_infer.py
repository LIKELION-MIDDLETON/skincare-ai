"""학습된 CNN 체크포인트로 피부 이미지를 분류하는 추론 모듈 (1차 판단)."""

import json
from pathlib import Path
from typing import Union

import torch
import torch.nn.functional as F
from PIL import Image

import config
from cnn_model import build_model, get_transforms


class SkinCNNPredictor:
    """학습된 CNN 체크포인트를 로드해 피부 이미지를 분류한다."""

    def __init__(
        self,
        checkpoint_path: Path = config.CHECKPOINT_PATH,
        class_names_path: Path = config.CLASS_NAMES_PATH,
        backbone: str = config.CNN_BACKBONE,
    ):
        self.device = torch.device(
            "cuda" if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available()
            else "cpu"
        )

        with open(class_names_path, "r", encoding="utf-8") as f:
            self.class_names = json.load(f)

        self.model = build_model(num_classes=len(self.class_names), backbone=backbone, pretrained=False)
        self.model.load_state_dict(torch.load(checkpoint_path, map_location=self.device))
        self.model.to(self.device)
        self.model.eval()

        self.transform = get_transforms(config.IMAGE_SIZE, train=False)

    def predict(self, image: Union[str, Path, Image.Image], top_k: int = 3) -> dict:
        """이미지 경로 또는 PIL.Image를 받아 예측 라벨/확률/상위 후보를 반환한다."""
        if isinstance(image, (str, Path)):
            image = Image.open(image).convert("RGB")
        else:
            image = image.convert("RGB")

        tensor = self.transform(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            logits = self.model(tensor)
            probs = F.softmax(logits, dim=1).squeeze(0)

        top_probs, top_idxs = torch.topk(probs, k=min(top_k, len(self.class_names)))

        ranked = [
            {"label": self.class_names[idx], "confidence": round(prob.item(), 4)}
            for prob, idx in zip(top_probs, top_idxs)
        ]

        return {
            "predicted_label": ranked[0]["label"],
            "confidence": ranked[0]["confidence"],
            "top_k": ranked,
        }
