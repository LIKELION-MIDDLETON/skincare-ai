# 데이터 갱신 파이프라인

신제품 출시·리뷰 변동을 반영해 추천 데이터를 갱신합니다.

## 전체 실행
```bash
./run_update.sh              # 데이터만 갱신
./run_update.sh --retrain    # 모델까지 재학습
```

## 단계별

| 순서 | 스크립트 | 하는 일 | 소요 |
|---|---|---|---|
| 1 | `fetch_products.py` | 카테고리별 상품 목록 + 전성분 | 10~20분 |
| 2 | `build_features.py` | 전성분 → 효능 15축 + 코메도·향료 | 1분 |
| 3 | `fetch_reviews.py` | 리뷰 집계 라벨 (`/stats` API) | 2~5분 |
| 4 | `rebuild.py` | 모델 예측 → `적합도_전상품.csv` | 10초 |

현재 추천 패키지는 토너·로션·크림뿐 아니라 클렌저/리무버, 에센스/세럼,
선케어, 마스크/팩, 미스트/특수케어까지 8개 카테고리 슬롯을 사용합니다.

## 권장 주기

| 항목 | 주기 | 명령 |
|---|---|---|
| 리뷰 라벨 | 주 1회 | `fetch_reviews.py` → `rebuild.py` |
| 신제품 | 월 1회 | `run_update.sh` |
| 모델 재학습 | 분기 1회 | `run_update.sh --retrain` |

## 증분 갱신
`--only-new` 옵션을 쓰면 기존 CSV에 없는 상품만 상세 조회합니다.
전체 재수집(20분)이 아니라 신규분만(1~2분) 처리됩니다.

## 자동화 예시 (cron)
```
# 매주 월요일 새벽 4시 리뷰 갱신
0 4 * * 1 cd /srv/recommend-api/updater && python3 fetch_reviews.py --products 피처.csv --out 리뷰라벨.csv && python3 rebuild.py --features 피처.csv --labels 리뷰라벨.csv --out ../적합도_전상품.csv

# 매월 1일 새벽 3시 전체 갱신 + 재학습
0 3 1 * * cd /srv/recommend-api/updater && ./run_update.sh --retrain
```

## 주의
- **동시 요청 수(`--workers`)를 함부로 올리지 마세요.** 기본 6~8이 적정합니다.
- 갱신 후 API 재시작이 필요합니다 (CSV를 기동 시 로드하므로).
- 크롤링은 서버에서 직접 실행해야 합니다.

## 리뷰가 쌓이면 자동으로 정확해집니다
리뷰 30건 미만 제품은 모델이 성분으로 **예측**하고,
30건을 넘으면 자동으로 **실측** 라벨로 전환됩니다.
`적합도_전상품.csv`의 `출처` 컬럼으로 확인 가능합니다.
