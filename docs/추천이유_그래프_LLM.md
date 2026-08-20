# 추천 이유 설명 (그래프 grounding + LLM)

> `/recommend` 응답의 `구성[].추천이유`에 "이 상품을 왜 추천했는지"를 자연어로
> 채워 넣는 기능. `graph/`(상품-성분-기능 그래프)에서 뽑은 사실만 LLM에 넘겨
> grounding하고, 요청마다 실시간으로 생성한다.

## 배경

`ml_engine.recommend()`는 진단마다 가중치가 다른 효능 축(`package_rules.DX[dx]["w"]`,
예: 여드름 진단이면 `여드름:3.0, 피지조절:2.5, 진정:2.5`)으로 상품 점수를 매기지만,
결과에는 점수만 있고 "왜"가 없었다. 반면 `graph/`에는 이미
`Product -[CONTAINS]-> Ingredient -[HAS_FUNCTION]-> Function` 그래프와, 식약처가
직접 인정한 `Product -[CLAIMS]-> Function` 엣지가 있는데 추천 로직이 이걸 안 쓰고
있었다(점수 계산은 `상품별_효능_v4.csv`의 집계 수치만 사용).

## 설계

### 1. 그래프에서 근거만 뽑기 — `graph_reasons.py`

서버 기동 시 1회 `graph/ingredient_nodes.csv`, `ingredient_has_function.csv`,
`product_contains_ingredient.csv`, `product_claims_function.csv`를 읽어 인덱스를
만든다(약 1.6초, 60MB — `ml_engine.products()`와 같은 지연 로드+캐시 패턴).

`evidence_for(goods_no, functions)`는 그 상품의 전성분 중 관심 효능(`functions`)과
겹치는 것만, 성분 하나당 근거 하나(가장 강한 것)로 추려서 반환한다. 정렬 기준은
① 근거 강도(`regulatory` > `official_reference` > `heuristic`), ② 전성분 표기 순서
(대략 함량 순). **관심 효능은 `DX[dx]["w"]`에서 가중치가 양수인 축만 쓴다** —
점수 계산에 실제로 반영된 축과 설명 근거를 일치시키기 위해서다(음수 가중치는
"이 효능은 피해야 함"이라 추천 이유가 될 수 없음).

### 2. LLM 문장화 — `llm_reasons.py`

`model/llm_analyzer.py`와 동일한 OpenAI 구조화 출력(`response_format=PackageReasons`)
패턴. 패키지(최대 7개 슬롯) 전체를 **한 번의 LLM 호출**로 묶어서 보낸다 — 아이템마다
호출하면 지연시간·비용이 슬롯 수만큼 선형으로 늘어나서다.

시스템 프롬프트가 강제하는 것:
- 주어진 성분 근거·직접 주장 목록에 없는 효능/성분은 언급 금지(할루시네이션 방지).
- `regulatory`/`official_reference` 근거는 단정적으로, `heuristic`(이름 기반 추론)
  근거는 완곡한 톤("~로 알려져 있다")으로 — 근거 강도를 문장 톤에 반영.

### 3. 실행 위치 — 루트(`ml_engine.py`/`main.py`)

`docs/orchestration.md`가 아직 미확정(옵션 A/B/C)인 것과 별개로, 이 기능은
**루트에 자체 구현**했다(팀 결정). `model/`의 `OPENAI_API_KEY`·`openai` 의존성과는
독립적으로 루트 `requirements.txt`/`.env`에도 동일한 키를 추가했다. `model/`과
언젠가 합쳐지면(옵션 A) 두 곳의 OpenAI 클라이언트 초기화를 정리할 여지가 있다.

### 4. 생성 방식 — 요청마다 실시간(캐시 없음)

같은 (진단, 상품) 조합이 여러 사용자에게 반복돼도 캐시하지 않고 매 `/recommend`
호출마다 새로 생성한다(팀 결정). 응답 시간에 LLM 호출 지연(보통 1~3초)이 그대로
더해지고, 호출 횟수만큼 OpenAI 비용이 발생한다. 트래픽이 늘면 `(진단, goods_no)`
키로 캐시하는 걸 재검토할 수 있다.

### 5. 실패 시 처리

`ml_engine.attach_reasons(r)`은 그래프에 근거가 하나도 없는 상품은 애초에 LLM
페이로드에서 빼고(빈 근거로 문장을 지어내지 않음), OpenAI 호출 자체가 실패하면
(키 없음, 네트워크 오류, 쿼터 초과 등) 예외를 삼키고 로그만 남긴 뒤 그대로
반환한다 — `구성[].추천이유`가 전부 `null`이 될 뿐, 가격·구성 등 핵심 추천 응답은
이 기능과 무관하게 항상 200으로 나간다.

## 응답 예시

```json
{
  "goods_no": "A000000209204",
  "name": "뉴트로지나 딥클린 페이셜 젤 클렌저",
  "일일가격": null,
  "판매가": 7100,
  "추천이유": "살리실릭애씨드가 식약처가 인정한 여드름 개선 성분으로 들어 있어 여드름 케어에 도움이 됩니다."
}
```

## 확인한 것

- `graph_reasons._load()` — 5,458개 상품 인덱싱, 약 1.6초/60MB.
- 여드름 진단 데모에서 살리실릭애씨드(`regulatory`, 여드름)가 올바르게 뽑히고,
  관련 근거가 없는 선케어 상품(선 미스트)은 LLM 페이로드에서 자동 제외됨을 확인.
- `OPENAI_API_KEY` 없이 `/recommend` 호출 — 200 응답, `추천이유` 전부 `null`,
  나머지 필드 정상(그래프 실패가 핵심 응답을 막지 않음 확인).
- 실제 OpenAI 호출로 생성된 문장 품질은 팀에서 키를 넣고 별도 확인 필요
  (이 세션에는 `OPENAI_API_KEY`가 없어 실호출 검증은 못 함).
