# 스킨케어 패키지 추천 API

피부분석 결과(CNN + LLM)와 설문 응답을 받아 **토너 → 로션 → 크림** 3단계 패키지를 추천합니다.

## 빠른 시작

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

브라우저에서 http://localhost:8000/docs 접속 → 바로 테스트 가능

### Docker
```bash
docker build -t skincare-api .
docker run -p 8000:8000 skincare-api
```

## 호출

```bash
curl -X POST http://localhost:8000/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "cnn_result": {
      "predicted_label": "acne_rosacea",
      "confidence": 0.9891,
      "top_k": [{"label":"acne_rosacea","confidence":0.9891}]
    },
    "survey": {"skin_type": 1, "concerns": [2,4,5], "irritation": 2}
  }'
```

## 엔드포인트
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 서버 상태 |
| GET | `/meta` | 클래스·설문 코드표 (모델팀 대조용) |
| POST | `/recommend` | 메인 |

## 문서
전체 스펙은 [백엔드_인계문서.md](./백엔드_인계문서.md) 참고.

## 구조
```
main.py            API 진입점, 입력 검증
survey_map.py      설문 → 효능 가중치 매핑
ml_engine.py       랭킹·제약·슬롯 조립
package_rules.py   진단별 케어 프로파일
적합도_전상품.csv    LightGBM 예측 결과 (5,523개)
상품별_효능_v4.csv   성분 효능 데이터
상품_용량.csv        상품별 총용량(올리브영 크롤링 원문 파싱, updater/build_capacity.py)
```

## 1일 사용량/가격
추천 결과의 각 아이템은 1주(7일) 사용을 가정해 총가격·총용량을 7로 나눈
**1일 가격(`일일가격`)**, **1일 사용량(`일일용량`)** 만 반환합니다(원본 총액·총용량은
응답에 포함되지 않습니다). 용량 데이터가 없는 상품은 `일일용량`이 `null`입니다.
패키지 전체 합계는 `총액_일일`(전체 1일 가격 합)로 제공됩니다.

```json
{
  "brand": "셀린저", "name": "셀린저 리얼 토너 씨벅톤 200ml",
  "일일가격": 1429, "일일용량": "28.6ml"
}
```

`상품_용량.csv`는 `oliveyoung_data/*/*.csv`의 `용량_증량` 원문(예: `"30ml*10"`,
`"본품 150mL / 증정기획..."`)에서 첫 번째 "숫자+단위" 토큰을 상품의 대표 용량으로
파싱합니다(개당×개수 배수 표기는 총량으로 환산). 재생성은
`python3 updater/build_capacity.py`.

## 모델
올리브영 리뷰 5,523개 집계 라벨로 학습한 LightGBM.
성분 → 적합도 6축(건성/지성/저자극/진정/보습/미백) 예측.

| 타깃 | R² |
|---|---|
| 미백효과 | 0.655 |
| 보습효과 | 0.527 |
| 진정효과 | 0.515 |
| 지성적합 | 0.476 |
| 건성적합 | 0.406 |
| 저자극 | 0.326 |

실측 4,277개 / 모델 예측 1,246개.

