"""CNN 전이학습 스크립트.

데이터 구조 (ImageFolder 형식):
    data/train/<클래스명>/*.jpg
    data/val/<클래스명>/*.jpg

실행 예:
    python train_cnn.py --data_dir data --epochs 15 --backbone efficientnet_b0
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import torch
from torch import nn, optim
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder

import config
from cnn_model import build_model, get_transforms


def compute_class_weights(train_ds: ImageFolder) -> torch.Tensor:
    """클래스별 샘플 수에 반비례하는 가중치를 계산한다 (희소 클래스가 무시되지 않도록)."""
    counts = Counter(train_ds.targets)
    num_classes = len(train_ds.classes)
    total = len(train_ds.targets)
    weights = [total / (num_classes * counts[i]) for i in range(num_classes)]
    return torch.tensor(weights, dtype=torch.float32)


def evaluate(model, loader, device) -> float:
    model.eval()
    correct, total = 0, 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            preds = outputs.argmax(dim=1)
            correct += (preds == labels).sum().item()
            total += labels.size(0)
    return correct / total if total else 0.0


def train(data_dir: Path, epochs: int, batch_size: int, lr: float, backbone: str, resume: bool = False) -> None:
    device = torch.device(
        "cuda" if torch.cuda.is_available()
        else "mps" if torch.backends.mps.is_available()
        else "cpu"
    )
    print(f"device: {device}")

    train_ds = ImageFolder(data_dir / "train", transform=get_transforms(config.IMAGE_SIZE, train=True))
    val_ds = ImageFolder(data_dir / "val", transform=get_transforms(config.IMAGE_SIZE, train=False))
    class_names = train_ds.classes
    print(f"클래스: {class_names}")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=2)

    model = build_model(num_classes=len(class_names), backbone=backbone, pretrained=True).to(device)
    class_weights = compute_class_weights(train_ds).to(device)
    print(f"클래스 가중치: {dict(zip(class_names, class_weights.tolist()))}")
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = optim.AdamW(model.parameters(), lr=lr)

    best_acc = 0.0
    config.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    if resume:
        if not config.CHECKPOINT_PATH.exists():
            raise FileNotFoundError(f"{config.CHECKPOINT_PATH} 없음. --resume 없이 먼저 학습하세요.")
        model.load_state_dict(torch.load(config.CHECKPOINT_PATH, map_location=device))
        best_acc = evaluate(model, val_loader, device)
        print(f"체크포인트에서 이어서 학습. 기존 val_acc={best_acc:.4f}")

    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * images.size(0)

        train_loss = running_loss / len(train_ds)
        val_acc = evaluate(model, val_loader, device)
        print(f"[Epoch {epoch + 1}/{epochs}] train_loss={train_loss:.4f} val_acc={val_acc:.4f}")

        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(model.state_dict(), config.CHECKPOINT_PATH)
            with open(config.CLASS_NAMES_PATH, "w", encoding="utf-8") as f:
                json.dump(class_names, f, ensure_ascii=False, indent=2)

    print(f"학습 완료. 최고 검증 정확도: {best_acc:.4f}")
    print(f"체크포인트 저장 위치: {config.CHECKPOINT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="피부 이미지 CNN 전이학습")
    parser.add_argument("--data_dir", type=str, default=str(config.DATA_DIR))
    parser.add_argument("--epochs", type=int, default=config.EPOCHS)
    parser.add_argument("--batch_size", type=int, default=config.BATCH_SIZE)
    parser.add_argument("--lr", type=float, default=config.LEARNING_RATE)
    parser.add_argument("--backbone", type=str, default=config.CNN_BACKBONE)
    parser.add_argument("--resume", action="store_true", help="기존 checkpoints/cnn_best.pt에서 이어서 학습")
    args = parser.parse_args()

    train(Path(args.data_dir), args.epochs, args.batch_size, args.lr, args.backbone, resume=args.resume)
