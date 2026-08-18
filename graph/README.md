# 상품-성분-기능 그래프

기본 구조는 다음과 같습니다.

`상품(Product) -[CONTAINS]-> 성분(Ingredient) -[HAS_FUNCTION]-> 기능(Function)`

식약처 기능성화장품 보고품목과 올리브영 상품명이 정규화 후 완전히 일치하는 경우에는 별도로 다음 엣지를 제공합니다.

`상품(Product) -[CLAIMS]-> 기능(Function)`

## 파일

- `product_nodes.csv`: 상품 노드. `product_id`는 올리브영 `goods_no`입니다.
- `ingredient_nodes.csv`: KCIA+식약처 병합 성분 노드와 매칭되지 않은 올리브영 원문 성분 노드입니다.
- `function_nodes.csv`: 기능/배합목적 노드입니다.
- `product_contains_ingredient.csv`: 상품의 전성분 엣지. `ingredient_order`는 원문 표기 순서입니다.
- `ingredient_has_function.csv`: 성분-기능 엣지입니다. `source`와 `evidence_strength`로 근거 수준을 구분합니다.
- `product_claims_function.csv`: 식약처 기능성화장품 보고품목과 상품명이 완전 일치한 직접 주장 엣지입니다.
- `manifest.json`: 생성 시각, 입력 데이터, 행 수, 성분 매칭 통계입니다.

## 근거 수준

- `KCIA / official_reference`: 성분사전의 배합목적 기반 연결
- `MFDS_GOSI / regulatory`: 식약처 기능성 성분 고시 기반 연결
- `RULES / heuristic`: 성분명 규칙 기반 추론. 추천 시 공식 근거와 분리해서 사용해야 합니다.
- `MFDS_REPORT / regulatory`: 식약처 기능성화장품 보고품목의 상품 직접 주장

## 재생성

프로젝트 루트에서 다음을 실행합니다.

```bash
python3 updater/build_graph.py
```

현재 그래프는 원천 데이터가 갱신될 때 재생성하는 CSV 형태이며, 이후 Neo4j/NetworkX 등에 적재할 수 있습니다.
