"""CNN 백본 정의 (사전학습 모델 전이학습)."""

import torch.nn as nn
from torchvision import models, transforms

_BACKBONES = {
    "resnet50": (models.resnet50, models.ResNet50_Weights.DEFAULT, "fc"),
    "efficientnet_b0": (models.efficientnet_b0, models.EfficientNet_B0_Weights.DEFAULT, "classifier"),
}


def build_model(num_classes: int, backbone: str = "efficientnet_b0", pretrained: bool = True) -> nn.Module:
    """사전학습된 backbone을 불러와 마지막 분류층만 num_classes에 맞게 교체한다."""
    if backbone not in _BACKBONES:
        raise ValueError(f"지원하지 않는 backbone: {backbone}. 사용 가능: {list(_BACKBONES)}")

    ctor, weights, head_attr = _BACKBONES[backbone]
    model = ctor(weights=weights if pretrained else None)

    if head_attr == "fc":
        in_features = model.fc.in_features
        model.fc = nn.Linear(in_features, num_classes)
    else:  # efficientnet류: classifier가 Sequential
        in_features = model.classifier[-1].in_features
        model.classifier[-1] = nn.Linear(in_features, num_classes)

    return model


def get_transforms(image_size: int = 224, train: bool = True):
    """학습/추론용 이미지 전처리 파이프라인."""
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

    if train:
        # DermNet(스튜디오 임상사진)과 normal 소스(폰카 셀카) 간 촬영 스타일 차이에
        # 모델이 과적합하지 않도록 조명/색감/블러 증강을 강하게 준다.
        return transforms.Compose([
            transforms.RandomResizedCrop(image_size, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.05),
            transforms.RandomGrayscale(p=0.05),
            transforms.RandomApply([transforms.GaussianBlur(kernel_size=5, sigma=(0.1, 2.0))], p=0.2),
            transforms.ToTensor(),
            normalize,
        ])

    return transforms.Compose([
        transforms.Resize(int(image_size * 1.14)),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        normalize,
    ])
