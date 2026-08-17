#!/usr/bin/env bash
# 데이터 갱신 파이프라인 (서버에서 실행)
set -e
cd "$(dirname "$0")"

echo "[1/4] 상품 목록·전성분 수집 (신규만)"
python3 fetch_products.py --out 상품원본.csv --only-new

echo "[2/4] 성분 -> 효능 변환"
python3 build_features.py --raw 상품원본.csv --out 피처.csv

echo "[3/4] 리뷰 라벨 수집"
python3 fetch_reviews.py --products 피처.csv --out 리뷰라벨.csv

echo "[4/4] 적합도 재생성"
python3 rebuild.py --features 피처.csv --labels 리뷰라벨.csv --out ../적합도_전상품.csv "$@"

cp 피처.csv ../상품별_효능_v4.csv
echo "완료. API 재시작하면 반영됩니다."
