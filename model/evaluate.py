"""검증셋(data/val)에 대해 학습된 CNN의 혼동행렬(confusion matrix)을 출력한다.

실행:
    python evaluate.py
"""

import json

import matplotlib.pyplot as plt
import torch
from sklearn.metrics import confusion_matrix, classification_report
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder

import config
from cnn_model import build_model, get_transforms


def main():
    device = torch.device(
        "cuda" if torch.cuda.is_available()
        else "mps" if torch.backends.mps.is_available()
        else "cpu"
    )

    with open(config.CLASS_NAMES_PATH, "r", encoding="utf-8") as f:
        class_names = json.load(f)

    val_ds = ImageFolder(config.DATA_DIR / "val", transform=get_transforms(config.IMAGE_SIZE, train=False))
    val_loader = DataLoader(val_ds, batch_size=config.BATCH_SIZE, shuffle=False, num_workers=2)

    model = build_model(num_classes=len(class_names), backbone=config.CNN_BACKBONE, pretrained=False)
    model.load_state_dict(torch.load(config.CHECKPOINT_PATH, map_location=device))
    model.to(device).eval()

    all_preds, all_labels = [], []
    with torch.no_grad():
        for images, labels in val_loader:
            images = images.to(device)
            preds = model(images).argmax(dim=1).cpu()
            all_preds.extend(preds.tolist())
            all_labels.extend(labels.tolist())

    cm = confusion_matrix(all_labels, all_preds, labels=range(len(class_names)))

    # 텍스트 출력
    col_width = max(len(c) for c in class_names) + 2
    header = " " * col_width + "".join(f"{c[:8]:>10}" for c in class_names)
    print("행: 실제 라벨 / 열: 예측 라벨\n")
    print(header)
    for i, row in enumerate(cm):
        print(f"{class_names[i]:<{col_width}}" + "".join(f"{v:>10}" for v in row))

    print("\n" + classification_report(all_labels, all_preds, target_names=class_names, digits=3))

    # 이미지로도 저장
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(class_names)))
    ax.set_yticks(range(len(class_names)))
    ax.set_xticklabels(class_names, rotation=45, ha="right")
    ax.set_yticklabels(class_names)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion Matrix (val)")
    for i in range(len(class_names)):
        for j in range(len(class_names)):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.colorbar(im)
    fig.tight_layout()
    out_path = config.BASE_DIR / "confusion_matrix.png"
    fig.savefig(out_path, dpi=150)
    print(f"\n혼동행렬 이미지 저장: {out_path}")


if __name__ == "__main__":
    main()
