# ADR-CF-H: 탐색 지평(Search Horizon) 확장 설계 청사진

- 상태: Proposed (Specialist 자문안, Karmack TDD 인계 대기)
- 기준선: `creative_agent` 89 passed (P0 + 3-Contract + 창의성 Phase 0~4)
- 근거: `harness.py / archive.py / qd.py / dsl.py / redteam.py / evaluator.py / contracts.py / creativity/{niche_space,isomorphism,operators,metrics}.py` 직접 판독 + 본 자문에서 수행한 **실측 프로브 4종**(§1 표의 "실측" 표기)
- 이 문서는 코드를 변경하지 않는다. 모든 제안은 기존 불변식 G1~G12 위에 **추가**되며, 3개 Protocol(DomainAdapter / VerificationOracle / BehaviorExtractor)은 동결 유지한다.

---

## 0. 결론 요약 (Executive Summary)

**Q1. 지평을 넓히면 창의적 추론에 도움이 되는가?** — **조건부 Yes.**

1. 지평은 창의성의 *필요조건*이다. QD 아카이브가 도달 가능한 최대 신규성은 (생성 가능 공간 ∩ 검증 가능 공간 ∩ 거동 구분 가능 공간)의 크기로 상한이 정해진다. 이 셋 중 하나라도 좁으면 나머지를 아무리 키워도 헛돈다.
2. 그러나 *충분조건은 아니다.* 생성 지평만 넓히면 (a) 환각 표면적 증가, (b) 고차원 아카이브 희석, (c) 검증 비용 폭증이 발생한다. Boden의 3분류로 보면 CounterField는 **탐험적(exploratory)** 창의성은 부분적으로, **결합적(combinational)** 창의성은 12~22개 템플릿으로 얇게, **변형적(transformational: 공간 자체의 변경)** 창의성은 전혀 갖고 있지 않다.
3. **가장 중요한 실측 발견: 병목은 생성이 아니라 검증/표현이다.** 시스템은 "말할 수 있지만 검증할 수 없는" 영역(§1.1)이 넓다. 따라서 확장 순서는 **V(검증) ≥ R(표현) → B(거동) → O(연산) → D(도메인)** 이어야 한다. D와 O부터 넓히면 No Evidence, No Credit 원칙 하에서 신규 후보 대부분이 `unrewarded`로 버려져 투자 대비 수율이 0에 수렴한다.

**핵심 설계 원칙 (Horizon Law)**
> **생성기(Generator)는 얼마든지 넓히되, 심판(Judge)은 결정론적·LLM-free로 유지하고, 지평의 확장 자체도 증거로 승인한다.**
> - 생성 지평 확장 = 자유 (LLM·확률·외부지식 허용, 단 크레딧 없음)
> - 크레딧 지평 확장 = 검증기 확장과 *동시에만* 허용 (Verifier-Coverage Parity)
> - 지평 확장 승인 = 회귀 동일성 + 검증 패리티 + 수율 개선(ablation)이라는 증거를 통과해야 활성화

---

## 1. 현재 시스템의 지평별 진단 (실측 기반)

### 1.1 실측 프로브 결과 (재현: `/tmp/probe*.py`, `.venv/bin/python`)

| # | 실측 | 결과 | 함의 |
|---|------|------|------|
| P1 | Mock 하네스 60슬롯, CentroidNicheSpace | `duplicate_rate=0.9`, `niche_count=3` | 현재 지평에서 탐색이 3개 니치로 붕괴 (Mock 한계 감안해도 구조적 징후) |
| P2 | 컴파일된 DSL 구성 | 변수 타입 **bool 100%**, 이펙트 **`set True` 100%**, 액터 **environment 100%** | `dsl.py`는 int/float/enum, add/sub/toggle, player/adversary 액터를 지원하는데 **컴파일러(`compile_semantic_ir`)는 그 부분집합의 극히 일부만 방출** → DSL 자체는 이미 컴파일러보다 넓다 (공짜 확장 여지) |
| P3 | `increases` vs `enables` 컴파일 결과 | **가드 완전 동일**. `decreases≡prevents`(`required_value=False`)도 동일 (`dsl.py:644`) | 5개 relation이 의미적으로 **2클래스(요구/금지)** 로 붕괴. 정량(수준, 이득, 지연) 의미 소실 |
| P4 | 피드백 루프 `a→b→a→p` 컴파일 | 상태 1개, 간선 0개, `reachable_stuck_state` **FATAL** | 단조 `set True`만 있으므로 **순환 의존은 실행 불가 = 교착**. 즉 피드백 루프는 DSL이 표현 못 한다 |
| P5 | 자체 템플릿 22개(기본 12 + JSON 10)를 그대로 메커니즘으로 레드팀 | **20/22 통과, 실패 2개 = `niche_differentiation`(상호억제 루프), `phase_transition_hysteresis`(히스테리시스 루프)** | 이종 도메인 동형 사상의 *가장 흥미로운* 동역학(상호 억제·이력 현상)이 자체 레드팀에서 FATAL로 거절됨. 표현 지평이 도메인 지평의 상한을 깎고 있음 |
| P6 | 무작위 위상 변종 300개(맥락 차원 고정) | WL 구조지문 **297종** vs CentroidNicheSpace 중심점 **9개** | 7D 투영이 구조 다양성의 97%를 구별 못 함 (위상은 4개 스칼라로 압축됨) |
| P7 | 레드팀 비용 | 샘플링 3봇 **7.4 ms/후보**, **정확한 전수 BFS 0.9 ms/후보**(컴파일 DSL 상태 ≤192개) | 현재 규모에서 **샘플링 대신 정확 검증(model checking)이 더 싸다.** 검증 지평의 가장 싼 확장점 |
| P8 | 코드 판독 | `_select_parents`: `sorted(elites, key=candidate.id)[:2]` (`harness.py:92`) | "상위 엘리트 샘플링"이 아니라 **id 사전순 앞 2개 고정**. 적합도·호기심·QD 기여 어느 것도 반영 안 함 |

### 1.2 지평별 한계

**(a) 표현 지평 R** — 상한: `CausalLink` 5종 relation + 컴파일 시 bool/set 단조 전이
- 정량 의미 없음(P3), 시간·지연 없음, 확률 없음, 다중 에이전트 게임 없음(adversary 액터 미사용), 순환/피드백 실행 불가(P4).
- `dsl_program_to_mechanism`은 손실 변환이므로 DSL을 풍부하게 해도 역사상은 약화됨(Phase 1 caveat 재확인).

**(b) 연산 지평 O** — 상한: 레거시 프롬프트 6종 + Inversion + Blend + Dialectical, **round-robin** (`slot % len`)
- `scheduler` 파라미터는 존재하나 **미사용**(`harness.py:35,65`). 연산자 크레딧(`record_credit`)은 카운터일 뿐 선택에 피드백 안 됨.
- 부모 선택은 P8. 교배(crossover) 연산자 부재(OperatorContext는 부모 2개를 이미 공급하는데 쓰는 연산자 없음).
- **결정론적·LLM-free 구조 변이 연산자(노드 삽입/간선 재배선/서브그래프 이식)가 없다** — 모든 변이가 LLM 경유라 비용·환각 모두 최대.
- 실패 아카이브/수리 인큐베이터가 탐색 신호(디딤돌)로 쓰이지 않음.

**(c) 거동 지평 B** — 상한: 7D = 맥락 3(LLM 분류, 3단계 범주) + 위상 스칼라 4
- 맥락 3차원은 `describe_niche`가 **LLM 자기보고**로 채운다 → *니치 게이밍*(빈 니치에 맞춰 라벨링) 가능. 지금은 문제가 안 보이지만 지평을 넓힐수록 위험이 커진다.
- 위상 4스칼라만으로는 P6처럼 구조 다양성이 압축된다. `/10`, `/5` 정규화는 포화(clip)된다.
- **포착하지 못하는 잠재 거동 공간**:
  1. *실행 기반 거동*: 도달 가능 상태 수, 승리 경로 수/최단·최장 길이, 결정 지점 분기, 비가역성, 전략 다양성(서로 다른 최소 승리 집합 수), 착취 표면적
  2. *에이전시 구조*: 플레이어/환경/적대자 액션 비율, 정보 비대칭
  3. *시간 구조*: 지연, 시간 척도 분리(빠른·느린 루프)
  4. *의미 축*: 무엇에 관한 아이디어인가(임베딩 기반 의미 위치)
  5. *출처 계보*: 어느 도메인·템플릿·연산자에서 왔는가
  6. *견고성*: 교란 하에서 승리 유지율
- 신규성 점수는 **음성 아카이브(클리셰) 대비**로만 계산되고 **아카이브 내부 대비 신규성이 없다**(F3 유지). QD에서 "novelty search" 신호가 사실상 없다. 임베딩은 `HashEmbeddingProvider`(어휘 해시 프록시)라 의미 신규성이 아님.
- 아카이브가 니치당 엘리트 1개 + 중심점 추가 전용(G7)이라 국소 경쟁(local competition)이 없다.

**(d) 검증 지평 V** — 상한: Exploit/Fatigue/Chaos 3봇(+CEGIS 수리 엔진, 단 하네스 호출은 Phase 1 훅으로만)
- 샘플링 기반 → *부재 증명 불가*. P7처럼 정확 검증이 더 싼 규모인데 활용하지 않음.
- 검증 대상이 "교착/착취/피로/크래시"로 한정. 도달 불가 payoff, 불가피한 패배, 지배 전략, 비가역 함정, 활성도(liveness)는 없음.
- 적대자가 **고정 3종**(정적 레드팀) → 공진화 없음. `utility/appropriateness/coherence`는 여전히 `provider.assess`(LLM) 의존 = 유일하게 주관적인 지점.
- 점수 `novelty`의 구조 비교는 `jaccard(링크 집합)`(문자열 일치) 기반이라 재라벨링에 취약(G4가 크레딧 단계에서만 보완).

**(e) 도메인 지평 D** — 상한: 기본 12 + JSON 10 = 22 템플릿(수작업)
- JSON 10개는 **하네스에 배선되어 있지 않다**(`TemplateLibrary.from_json`은 테스트에서만 호출, 테스트에 절대경로 하드코딩 `test_curated_templates.py:6`).
- `TemplateLibrary.match`는 **3개 불리언 모티프** 겹침으로만 순위를 매겨 변별력이 극히 낮음(동점은 id 순).
- 템플릿 vocab 블랙리스트도 수작업. 외부 지식 유입 경로가 없다. 베이스라인 클리셰도 LLM이 생성(외부 선행기술 근거 없음).

---

## 2. 지평 확장 아키텍처 (ADR 결정 사항)

용어: 후보가 얻는 증거 등급을 **크레딧 티어**로 명시한다. (기존 "unrewarded, not blocked" 원칙의 구체화이며 새 우회로가 아니다. 기존 ACCEPTED 판정은 바꾸지 않고 *창의 크레딧*만 구분한다.)

| 티어 | 의미 | 부여 주체 |
|------|------|-----------|
| T0 | 생성됨, 미검증 | 없음 (로그만) |
| T1 | 구조 검증 통과 (graph/WL/모노모피즘) | 기존 Verifier |
| T2 | **완전 탐색으로 증명된** 성질 (`complete=True`) | 신규 ExactOracle |
| T3 | 외부 근거(출처 해시+원문 인용)와 구조 일치 | 신규 Provenance Verifier |

### ADR-H0. Horizon Ledger (측정 먼저) — 지평 계기판
지평 확장은 측정 없이 하지 않는다. `CreativeMetrics`를 확장해 지평별 지표를 `HarnessResult.metrics`에 추가한다(키 추가만, 기존 키 불변).

| 지평 | 지표 |
|------|------|
| R | `dsl_fragment_rate`(비-bool/비-set 요소를 쓴 후보 비율), `relation_class_entropy`, `uncompilable_motif_rate` |
| O | `operator_entropy`, `operator_yield[name]`(=T1+ 크레딧/제안), `parent_gini`(부모 선택 편중), `graph_edit_share` |
| B | `niche_count`, `qd_score`, **`collapse_ratio`**(= 구별 WL 클래스 수 / 점유 중심점 수; P6에서 297/9≈33), `effective_dims`(=참여비 PR, 아래 식), `internal_novelty`(아카이브 내부 kNN 거리) |
| V | `exact_coverage`(T2 판정 비율), `inconclusive_rate`, `adversary_pool_size`, `revocations` |
| D | `template_domains`, `template_sources`, `domain_distance_mean`(채택 템플릿↔문제), `quarantined_templates` |

`effective_dims = (Σλᵢ)² / Σλᵢ²` (λ: 아카이브 거동벡터 공분산의 고유값). 7D가 실질 2~3D로 접혀 있는지 진단.

### 2.1 V — 검증 지평 확장 (최우선)

**H-V1. `ExactReachabilityOracle` (CompositeOracle로 구현, Protocol 동결)**
- `VerificationOracle`을 구현하는 래퍼. 내부에 기존 `DefaultVerificationOracle`을 위임하고, `EvaluationBundle.diagnostics.playtest_report.issues`에 **정확 검증 이슈**를 *추가*만 한다(기존 이슈 삭제 금지).
- 알고리즘: 컴파일된 `DSLProgram`의 명시적 상태 전수 탐색(BFS, 상태 캡 `N_MAX=200_000`, 키는 `_state_key`). 결과는 3값: `PROVEN / REFUTED(witness) / INCONCLUSIVE`.
- 신규 FATAL 이슈(모두 **재생 가능한 witness** 동반 → 기존 `replay_counterexample`/`Counterexample`로 CEGIS·변증법과 직결):
  - `payoff_unreachable` (승리 상태 도달 불가) — 현재는 일부만 stuck으로 간접 포착
  - `forced_loss` (적대자 최적 응답 시 승리 불가; 게임 이론 attractor 계산, §2.2 R3과 결합)
  - `dominant_trivial_strategy` (길이 ≤ k 단일 경로가 항상 승리)
  - `irreversible_trap` (승리 도달 가능 상태에서 도달 불가 상태로 가는 간선)
- `INCONCLUSIVE`(상태 캡 초과)는 **통과가 아니다**: 후보는 기존 샘플링 결과로만 판정되고 T2 크레딧은 없다. 이것이 G18.
- 비용: P7 실측 0.9 ms. 상태 폭발 시 증분 확장(심볼릭/SMT)은 장기 과제.
- 효과: 샘플링으로는 증명 불가였던 *부재*를 증명 → 지평 확장 시 환각 표면 증가를 가장 직접적으로 상쇄.

**H-V2. 메타모픽·차분 검증 (zero-network)**
- 동치 변환(노드 재라벨링, 독립 간선 순서 치환)에서 판정 불변, 단조 변환(간선 추가)에서 도달성 단조 — 위반 시 검증기 자체 결함 경보(`oracle_self_check_failures`). 검증기의 신뢰도 자체를 지평의 일부로 취급.

**H-V3. 공진화 레드팀 (CoRT: Co-evolutionary Red-Teaming)** — 중기
- 적대자 정책을 유전자(`AdversaryGenome`: 액션 우선순위 규칙, 반복 길이, 상태 조건부 선택 템플릿)로 두고 **별도 MAP-Elites**(행동 기술자: 착취 길이 × 상태 커버리지 × 자원 곡선)로 진화. 적합도 = 후보에 대한 "손상도"(승리/패배 도달 스텝 단축).
- **적대자는 생성기이지 심판이 아니다(G14).** 발견된 착취는 반드시 `Counterexample`(witness 재생 가능)로 환원되어야 FATAL이 된다. 적대자 풀은 **append-only**, 시드 고정 시 결정론(G8).
- 공진화 루프: 엘리트 후보 → 적대자 풀 재공격 → 새 witness → (a) 아카이브 탈락이 아니라 **Revocation 이벤트(G13)** + (b) Phase 1 변증법으로 환류(반례→규칙).
- POET/PAIRED 계열의 "학습 가능한 난이도" 아이디어를 차용하되, 심판은 DSL replay이므로 학습형 심판의 환각 위험 없음.

### 2.2 R — 표현 지평 확장

**H-R1. 컴파일러 확장 (DSL은 이미 충분히 풍부; 방출을 늘린다)** — 단기~중기
- *SemanticIR v2* (옵트인, 레거시 경로 byte-identical): `CausalLink`는 **불변**(frozen 5 relation) 유지하고, **사이드카 주석** `LinkAnnotation(link_index → {kind: level|boolean, gain, delay_ticks, saturation})`을 `CanonicalMechanism` 외부(`EvaluationBundle`/`IdeaCandidate.lineage` 확장 필드 또는 별도 sidecar 모델)에 둔다.
- 매핑 표(주석 있을 때만 적용):

| relation | 현 컴파일 | v2 컴파일 (주석 있을 때) |
|----------|-----------|--------------------------|
| enables / depends_on | 가드 `src==True` | 가드 `level(src) ≥ θ` |
| increases | 위와 동일 (P3) | 효과 `add(effect, gain)` (int, 경계 클램프) — 양의 피드백 가능 |
| decreases | 가드 `src==False` | 효과 `sub(effect, gain)` — **음의 피드백/감쇠** 가능 |
| prevents | 위와 동일 | 적대자/환경 액션 `set False`/`toggle` — 비단조 동역학 |

- 이로써 P4(루프 교착), P5(2개 템플릿 거절)의 근본 원인인 **단조성**을 해소. 루프가 "교착"이 아니라 "진동·안정·폭주" 성질로 분류된다.
- **함정**: `CanonicalMechanism.fingerprint`(G3 동결)는 주석을 포함하지 않으므로, 같은 그래프·다른 주석이 *중복으로 오판*된다. → v2 모드에 한해 `semantic_fingerprint = H(fingerprint, canonical(annotations))`를 별도 `seen_semantic` 집합에 사용(기존 `seen_mechanisms` 불변). G3·G4 침해 없음.

**H-R2. 시간·확률**
- `delay_ticks`: 환경 틱 액션으로 컴파일(`tick` 변수), 이산 시간 모델. 확률: 결과 분기를 **열거형 분기 + 가중치**로 두고 DTMC 정확 해석(결정론적; 샘플링 아님). 시간 척도 분리(빠른/느린 루프)가 새 거동 차원(§2.3)의 원료.

**H-R3. 다중 에이전트/게임**
- 현재 미사용 `adversary` 액터를 활성화: 플레이어 vs 적대자 교대 이동 게임에서 **attractor 계산(백워드 귀납)** 으로 `forced_loss`, 승리 전략 존재성 판정. 경매 템플릿(Vickrey 등)의 유인 적합성(IC) 같은 메커니즘 설계 성질을 검증 가능한 속성으로 승격.

**H-R4. DSL 메타-진화 = 보수적 확장(Conservative Extension) + 매크로 라이브러리 학습** — 장기
- **금지**: LLM이 새로운 *코어 의미론*(새 연산자 구현)을 작성해 인터프리터에 주입하는 것(= 심판 오염).
- **허용**: 아래 2단계만.
  1. *매크로 마이닝*: 승인된 엘리트들의 빈출 서브그래프/액션 패턴(RuleLibrary의 ≥2 독립 성공 승격 규칙 재사용)을 `Macro(name, params, expansion_in_core_DSL)`로 제안. 확장 결과가 코어 DSL이므로 **검증 건전성이 그대로 상속**된다(DreamCoder식 라이브러리 학습).
  2. *코어 의미론 확장*(예: 새 효과 연산): 사람(Karmack TDD) 구현 + 적합성 코퍼스 + 컴파일 불변식 + 레거시 회귀 byte-identical을 통과해야 `DSL_VERSION` 상향. ADR 이벤트로 취급.
- 매크로 승격 조건: 확장 전/후 oracle 판정 동일(G21), 독립 후보 ≥ 2, 인용 가능한 계보.
- 이것이 Boden의 *변형적* 창의성의 안전한 근사: 공간 자체를 바꾸되, 바뀐 공간이 이전 공간의 *보수적 확장*임을 증명 가능하게 만든다.

### 2.3 B — 거동 지평 확장

**H-B1. 실행 기반 거동 기술자 (`DynamicsV2`)** — 단기~중기
- ExactOracle의 탐색 부산물에서 **검증기가 관측한 값만**으로 기술자 생성(G15: LLM 자기보고 금지): `log2(reachable_states)`, `n_win_paths(log)`, `min/max_win_len`, `mean_decision_branching`, `irreversibility_index`, `strategy_diversity`(최소 승리 액션 집합 수), `agency_ratio`(player 액션 비율), `exploit_surface`.
- 기존 `DynamicalNicheDescriptor`는 동결; **별도 optional capability Protocol** `ExecutableDynamicsExtractor.extract_exec(candidate, exact_report)`를 추가하고 `isinstance`로 발견(§2.6, Protocol 동결 규칙 준수).
- 맥락 3차원(LLM 분류)은 가능한 한 DSL에서 **유도**(예: intervention_level ← 액터 분포/노드 도메인, feedback_horizon ← 최장 승리 경로·`delay_ticks`)하고, LLM 분류는 *교차검증용 보조*로 강등 → 니치 게이밍 차단.

**H-B2. 다중 렌즈 아카이브 (Multi-Lens Archive) — 가변 차원의 안전한 구현**
- 차원을 늘릴 때 기존 중심점을 재배치하면 G7(엘리트 단조성)이 깨진다. 따라서 **차원 추가 = 새 렌즈 추가**로 모델링한다.
- 설계: 승인(admission)은 **단일 문(G1)** 을 한 번 통과. 통과한 엔트리를 N개의 `Lens`(각자 `NicheSpace` + 엘리트 맵 + 스냅샷)에 인덱싱. 렌즈는 독립 append-only. 새 렌즈는 풀(reservoir+전체 승인 로그)에서 *결정론적 백필*로 초기화.
- 렌즈 후보: `topology`(현 7D), `executable`(§B1), `semantic`(§B4), `provenance`(도메인×템플릿×연산자), `robustness`.
- 지표: 렌즈별 `niche_count/qd_score`, 교차 렌즈 `joint_qd`. 원자성(G5): 모든 렌즈의 `snapshot/restore`를 `QDArchive._snapshot()`에 포함.
- 차원 확장 비용(희석) 대응: 렌즈마다 4~8D로 제한하고 렌즈 수를 늘린다(곱공간 폭발 방지) — 고차원 단일 격자보다 다중 저차원 렌즈가 MAP-Elites 희석에 강함.

**H-B3. NSLC (Novelty Search with Local Competition) — 선택 압력 렌즈**
- 아카이브 *저장*이 아니라 **부모 선택 점수**로만 사용: 각 엔트리의 `(novelty = k-NN 평균거리, local_competition = k-이웃 중 품질 순위 비율)`. 저장소는 여전히 G7을 지키는 centroid 렌즈. NSLC가 축출을 수반하므로 admission store로 쓰면 G7 위반 → **자문 전용(advisory)** 으로 격리.
- 아카이브 내부 신규성(`internal_novelty`)을 신규 `EvaluationScores` 필드가 아니라 **Ledger 지표+스케줄러 입력**으로만 노출(G6 Pareto 축 동결 유지). 파레토에 편입하려면 `dominates_v2` 버전 도입(§4 G6).

**H-B4. 의미 렌즈 (희소·고차원 임베딩 투영)**
- 임베딩 → 시드 고정 랜덤 투영(Johnson–Lindenstrauss, 8~16D) → 별도 `CentroidNicheSpace` 렌즈. 모델/투영 행렬 버전을 Ledger에 기록(G8). 희소 고차원은 LSH 버킷키를 니치키로.
- **이 렌즈는 크레딧을 부여하지 않는다**(임베딩은 통계적 휴리스틱이며 검증이 아니다). 다양성 *계측*과 부모 선택에만 사용. 의미 신규성은 구조 신규성(WL ≥4노드) AND 실행 신규성(B1)과 *동시 충족*할 때만 "신규" 집계 → 패러프레이즈 인플레이션 차단.

### 2.4 O — 연산 지평 확장

**H-O1. 부모/연산자 스케줄러 (즉시 적용 가능)** — `scheduler` 훅 활성화
```python
class Scheduler(Protocol):          # 새 optional capability, 3-Contract 불변
    def choose(self, slot: int, view: ArchiveView, ops: Sequence[CreativeOperator],
               rng_seed: int) -> tuple[int, tuple[IdeaCandidate, ...]]: ...
    def feedback(self, slot: int, op_name: str, parent_ids: tuple[str,...],
                 outcome: SlotOutcome) -> None: ...   # outcome: tier, Δqd, new_niche, error
```
- 기본값 `None` → 현재 round-robin + `pool[:2]` 와 byte-identical.
- 제안 정책 `CuriosityQDScheduler` (모두 `stable_hash(seed, slot)` 시드 RNG, G8):
  - 니치 점수 `s(n) = α/√(1+visits(n)) + β·EMA(Δqd_offspring(n)) + γ·pending_density(n) + δ·local_competition(n)`; 부모는 `softmax(s/τ)` 또는 UCB로 선택.
  - 연산자는 **슬레이트 밴딧**(Thompson/UCB): 보상 = *티어 가중 크레딧* (T0=0, T1=0.3, T2=0.7, T3=1.0)×`Δ(niche_count, qd_score)`. 실패(`*_errors`)는 음의 보상(G10).
  - 탐험 하한: 모든 연산자에 최소 `ε·budget` 예산 보장(밴딧 기아 방지, G11 예산 회계).
- 실패 활용: `repair_incubator`/`failure_archive`에서 "거의 성공" 엔트리(예: 품질 임계 미달만 실패)를 **디딤돌 부모**로 낮은 확률(`ρ_stepstone`)로 공급 — 단, 자식은 정상 파이프라인 전체를 통과해야 함(G1).

**H-O2. 결정론적 구조 변이/교배 연산자 군 (LLM-free)** — 단기
`GraphEditOperator` 서브클래스 (Zero-network, 시드 결정론, G9):
`SubdivideEdge`(간선 사이에 중개 노드 삽입), `RewireEdge`, `InsertMotif`(피드백 루프·완충 경로 삽입), `GraftSubgraph`(부모 B의 서브그래프를 부모 A에 이식 = 교차), `ContractPath`, `PolarityFlip` (현 Inversion과 구분: LLM 없음).
- 라벨은 결정론적 합성 라벨(`{parentA}↔{parentB}:mid1`)로 두고, 의미 있는 이름·서술은 별도 `SemanticReskin`(LLM) 단계가 담당 — **reskin 결과는 구조 불변(그래프 동형 + 라벨만 변경) 검증 후 T0→T1**. 의미가 빈약한 구조 정크는 기존 `utility/appropriateness` 게이트가 걸러낸다.
- 효과: 후보당 LLM 호출 0~1회로 O(1) 비용의 구조 다양성 대량 공급(검증기가 병목이므로 H-V1과 쌍으로).

**H-O3. 합성 연산자 파이프라인 + 메타 스케줄링**
- `Pipeline([Blend, GraphEdit, Inversion])`: 연산자 조합을 1급 객체로. 조합 깊이는 G12(재귀 캡)로 ≤3. 어떤 조합이 수율이 높은지 밴딧이 학습.

### 2.5 D — 도메인 지평 확장

**H-D1. 근거 결박형 템플릿 컴파일 파이프라인 (ETL, 하네스 외부 프로세스)**

```
[Acquire] → [Extract] → [Normalize] → [Verify] → [Quarantine] → [Promote]
 오프라인     구조적/텍스트   CausalTemplate  결정론 게이트   status=candidate   ≥2 독립 근거 or
 스냅샷+해시   이원 추출      + provenance                    BlendOperator       큐레이터 서명
```
1. **Acquire** (유일하게 네트워크 허용; 별도 프로세스/CLI `counterfield-ingest`): 스냅샷 + `sha256` + 라이선스 + 취득일을 `data/templates/_sources/manifest.json`에 고정. 하네스는 스냅샷만 읽는다(**G17: 하네스 zero-network 유지**).
2. **Extract** — 두 경로를 구분:
   - *구조적 소스(우선)*: 부호 있는 방향 그래프가 이미 있는 DB는 LLM이 필요 없다. 후보 소스:
     - **SIGNOR / Reactome / KEGG / BioPAX** (분자 신호전달의 활성화·억제 부호 인과) → `increases/decreases/enables/prevents`에 직결
     - **SBML BioModels** (실행 가능한 ODE 모델) → 상호작용 그래프 추출 + 루프 부호
     - **시스템 다이내믹스 인과 루프 다이어그램(CLD)** (Vensim/Stella 공개 모델; 극성+루프 유형 명시) → 경제·정책 도메인
     - **Web of Life / 먹이그물 데이터셋**(생태), **Petri net(PNML)** (자원·병행 구조)
   - *텍스트 소스(arXiv 초록 등)*: LLM 추출은 허용하되 **리터럴 인용 가드(Inversion의 `evidence_quote` 방식)**: 각 링크에 원문 `evidence_span`(오프셋) 필수, NFKC+casefold 후 `cause`·`effect` 토큰이 인용구에 *문자열로* 존재해야 함. 인용 없는 링크는 폐기(환각 가드).
3. **Normalize**: `CausalTemplate`에 `provenance: {source_id, snapshot_sha256, license, evidence_spans[], extractor_version}` 추가(모델 필드 추가는 기본값 있는 선택 필드 → 기존 JSON 호환). `domain_vocabulary`는 노드 라벨 + 코퍼스 TF-IDF 상위 토큰에서 **자동 생성**(수작업 블랙리스트 탈피).
4. **Verify (결정론 게이트)**: (i) 노드 ≥4, 약연결, 부호 일관(자기 모순 루프 없음), (ii) 구조 중복 제거(WL 지문, 기존 템플릿과 동일하면 폐기), (iii) **DSL(v2) 컴파일 가능성 + 템플릿 단독 레드팀/ExactOracle 통과**(P5 교훈: 실행 불가 템플릿은 쓸모없음), (iv) 인용 가드, (v) 모티프 재계산(선언된 `motifs`와 `MotifExtractor` 결과 일치).
5. **Quarantine → Promote**: 신규 템플릿은 `status=candidate`로 BlendOperator에서 **T0 전용**(사용 가능, 크레딧 없음). `RuleLibrary`와 같은 규칙: *독립 후보 ≥2가 T1+ 검증 성공* 또는 큐레이터 서명 시 `promoted`. 승격 전까지 `match()`에서 낮은 가중.
6. **목표 규모와 선택**: 22 → 200~500. 단순 증량이 아니라 **한계 커버리지 최대화**(그리디: 모티프 벡터 공간에서 기존 템플릿 집합과의 최소 거리가 큰 순) + 도메인 수 ≥ 15.

**H-D2. 풍부한 모티프 매칭** — 단기
- `MotifProfile` 3불리언 → **모티프 벡터**: 부호별 피드백 루프 수(양/음), SCC 크기 분포, 피드포워드 루프(FFL)·bi-fan 같은 네트워크 모티프 수, 차수열 요약, WL 라벨 히스토그램(k=2). 점수 = 코사인 유사도, 후보 템플릿 상위 k만 정확 모노모피즘 검증(§기존 5게이트). 기존 `MotifProfile`은 동결, `MotifVector`는 신규 병행 타입.
- *도메인 거리 선호*: 문제 도메인과 **먼** 템플릿을 우대(도메인 거리 = 소스 온톨로지 경로/임베딩 거리). 원거리 전이가 창의성의 원천이므로 가까운 도메인의 표면 유사 위험은 기존 vocab 블랙리스트 + G4가 계속 차단.

**H-D3. DomainPack (도메인 플러그인)**
- `DomainPack = (templates, vocabulary, extra_oracle_checks, extra_extractors)`. 예: 열역학 팩은 보존법칙 단위 검사, 경매 팩은 IC 검사. 팩 로딩은 적합성 테스트 통과 필수, 계약은 **optional capability Protocol** 로 발견.

**H-D4. 선행기술 오라클 (신규성 판정의 외부 근거)** — 장기
- 현재 신규성은 LLM이 생성한 클리셰 baseline 대비뿐. 오프라인 코퍼스 스냅샷(arXiv/특허 메타) 위 BM25+구조지문 질의로 `PriorArtVerifier` 구현: 근접 선행기술 발견 시 신규성 *감점*(근거 링크 동반). 네트워크는 ingest에서만(G17). 신규성 크레딧의 외부 접지를 제공.

### 2.6 계약 동결 준수 (구현 규칙)
- 3개 Protocol 시그니처 불변. 모든 확장은 (1) 별도 `@runtime_checkable` capability Protocol(`ExactCapable`, `ExecDynamicsCapable`, `SchedulerLike`, `LensProvider`) + (2) `IdeationHarness.__init__`의 **키워드 전용·기본 None** 인자 + (3) None일 때 byte-identical.
- 모든 신규 상태(스케줄러 통계, 렌즈, 적대자 풀, 규칙 라이브러리 확장)는 `archive._snapshot()/_restore()` 또는 `on_admit` 트랜잭션에 포함(G5).

---

## 3. 로드맵

각 PR은 (i) 비활성 시 기존 89 tests byte-identical (ii) 신규 불변식 테스트 (iii) Ledger 지표 노출을 DoD로 한다. 추정은 Karmack 기준 개략치.

### 단기 (S, 즉시 적용 가능 · 1~2주 · 기존 계약 무변경)
| ID | 작업 | 추정 | 수용 기준(DoD) |
|----|------|------|----------------|
| S1 | **Horizon Ledger** (H0) | 1d | 지표 키 추가만; 키 부재 시 기존 consumer 무영향; Mock 실행에서 `collapse_ratio` 산출 |
| S2 | **스케줄러/부모 선택** (H-O1) | 3d | `scheduler=None` 동일성; ScriptedBackend·고정 seed 5회 반복에서 `niche_count` 중앙값 ≥ 기준선×1.3 *또는* 동일 niche에서 `qd_score` ↑ (Mann–Whitney p<.1); 2회 실행 결정론 동일 |
| S3 | **템플릿 JSON 배선 + 병합** + 테스트 절대경로 제거 | 1d | 22개 로드, 중복 id·WL 중복 거부, 상대경로 |
| S4 | **ExactReachabilityOracle** (H-V1) | 3d | 22개 템플릿 + 300 무작위 변종에서 샘플링 결과와 모순 없음(샘플링이 FATAL이면 Exact도 FATAL 이상), `INCONCLUSIVE`≠pass, witness 재생 100% |
| S5 | **GraphEdit 연산자 3종**(Subdivide/Rewire/Graft) (H-O2) | 3d | 제로 네트워크, 시드 동일 → 동일 출력, 생성 후보의 T1 통과율 측정 |
| S6 | **모티프 벡터 매칭** (H-D2) | 2d | 기존 `match()` 결과가 새 매처의 부분 순서와 호환(회귀), 동점 해소율 ↑ |

### 중기 (M, 1~2개월)
| ID | 작업 | 수용 기준 |
|----|------|-----------|
| M1 | **SemanticIR v2 + DSL 방출 확장** (H-R1) | 주석 없을 때 byte-identical; P4 루프·P5 2개 템플릿이 통과 또는 *유의미한* 진동/안정 성질로 분류; `semantic_fingerprint` 중복 판정 테스트 |
| M2 | **DynamicsV2 + 다중 렌즈 아카이브** (H-B1, B2) | 렌즈 추가가 기존 엘리트를 변경하지 않음(G7·G19), 백필 결정론, `collapse_ratio` 감소 |
| M3 | **NSLC 자문 렌즈 + 내부 신규성** (H-B3) | 스케줄러 입력으로만 사용(저장 불변), ablation 유의 |
| M4 | **템플릿 ETL (구조적 소스 1~2종: SIGNOR + SBML 서브셋)** (H-D1) | 템플릿 ≥ 80개, 전량 provenance+해시+DSL 컴파일 검증, 격리→승격 규칙 테스트, 하네스 네트워크 소켓 0 |
| M5 | **CoRT 적대자 풀 + Revocation 원장** (H-V3, G13) | 적대자 풀 append-only, 모든 FATAL이 재생 가능 witness, 탈락이 아니라 이벤트로 기록 |
| M6 | 2-플레이어 attractor 검증 `forced_loss` (H-R3) | 경매 템플릿 IC 속성 검증 성공/실패 케이스 코퍼스 |

### 장기 (L, 분기 이상)
| ID | 작업 | 비고 |
|----|------|------|
| L1 | 매크로 라이브러리 학습 / DSL 메타-진화 (H-R4) | 코어 의미론 확장은 ADR 이벤트(사람 게이트) |
| L2 | 텍스트 소스 추출(arXiv) + 인용 가드 (H-D1 텍스트 경로) | 환각 가드 오탐/미탐률을 먼저 측정 후 활성화 |
| L3 | 확률·시간 모델 DTMC (H-R2) | 상태 폭발 시 SMT/심볼릭 도입 |
| L4 | 선행기술 오라클 (H-D4) | 오프라인 스냅샷 전제 |
| L5 | DomainPack 생태계 (H-D3) | |
| L6 | **문제 공진화(POET류)**: 문제 서술 자체를 변이해 "아직 풀리지 않은 하위 문제"를 아카이브 니치로 취급 | 심판은 동일(DSL replay) |

---

## 4. 불변식 충돌 분석 및 가드레일

### 4.1 기존 G1~G12와의 충돌

| 불변식 | 충돌 가능 제안 | 판정 | 가드/해법 |
|--------|----------------|------|-----------|
| G1 단일 승인문 | 스케줄러 디딤돌 부모, CoRT 환류, GraphEdit/Reskin 자식 | 충돌 없음(조건부) | 모든 자식은 `canonicalize → validate → evaluate → insert` 전체 경로. 우회 삽입 API 금지 |
| G2 미검증=무보상 | 템플릿 격리, 신규 연산자 | 강화됨 | 티어 도입으로 *보상 크기*를 증거 등급과 연결 |
| G3 지문 동결 | R1 주석 | **충돌 위험** | 주석은 지문에서 제외하고 `semantic_fingerprint`를 v2 모드 전용 집합에 사용 |
| G4 WL 지문(≥4노드) | GraphEdit 소규모 그래프 | 경미 | <4노드는 기존대로 면제, GraphEdit은 ≥4노드 보장 변이만 생성 |
| G5 원자성 | 렌즈·스케줄러 통계·적대자 풀·규칙 라이브러리 확장 | 관리 필요 | 전부 `snapshot/restore` 편입; 스케줄러 `feedback`은 `on_admit` 내부 또는 성공 후 커밋 |
| G6 파레토 축 동결 | `internal_novelty`, 거동 신규성, exploit_resistance 편입 욕구 | **충돌** | 기본은 Ledger/스케줄러에만 노출. 편입은 `dominates_v2`(버전 필드, 기본 v1)로만 |
| G7 엘리트 단조성 | NSLC(축출 수반), 차원 추가, **새 반례에 의한 탈락** | **충돌** | (a) NSLC/차원 추가는 별도 렌즈(저장 불변), (b) 신규 검증에 의한 탈락은 G7 위반이 아니라 **G13 Revocation**(명시적·로그·트랜잭션)으로 분리 |
| G8 시드 결정론 | 밴딧, 적대자 진화, 임베딩 투영 | 관리 필요 | 모든 RNG `stable_hash(seed, slot, ...)`; 임베딩 모델·투영 행렬 버전 고정/기록 |
| G9 제로 네트워크 | 템플릿 ETL, 선행기술 | **충돌** | ETL은 별도 프로세스·별도 엔트리포인트; 하네스는 스냅샷만 읽음(G17); 드라이런 소켓 0 테스트 유지 |
| G10 침묵 실패 금지 | Exact `INCONCLUSIVE`, 스케줄러 오류 | 강화 | `inconclusive_rate`, `scheduler_errors` 카운터 노출, 음의 보상 |
| G11 예산 회계 | 정확 검증·CoRT·재생 비용 | 관리 필요 | 검증 비용(상태 수, 재생 횟수)을 예산 단위로 환산·청구; `N_MAX` 하드캡 |
| G12 재귀 캡 | Pipeline·매크로·적대자 재공격 | 관리 필요 | 합성 깊이 ≤3, 매크로 중첩 ≤2, 동일 witness 해시 1회 |

### 4.2 신규 불변식 (제안)

- **G13 Revocation 원장**: 엘리트·템플릿·규칙의 철회는 *오직* 신규 증거(재생 가능 witness)에 의해, 명시적 `RevocationEvent{entry_id, verifier_epoch, witness_hash}`로만, 트랜잭션 내에서, append-only 로그로 수행. 침묵 삭제 금지. `verifier_epoch`는 검증기/적대자 풀 버전.
- **G14 생성기-심판 비대칭**: 확률적·LLM·외부지식 구성요소는 생성기에만. 크레딧을 결정하는 경로는 결정론적·LLM-free. 적대자·임베딩·NSLC는 *제안/선택*만, 판정 불가.
- **G15 기술자 순도**: 신규 거동 차원은 검증기 관측 산출물(그래프·실행 트레이스)에서만 유도. LLM 자기보고 라벨은 신규 차원 금지, 기존 3차원은 점진적으로 유도값으로 대체(교차검증 불일치율을 Ledger에 기록).
- **G16 템플릿 출처 결박**: 모든 템플릿은 `source_ref + snapshot_sha256 + evidence_span(s)`. 텍스트 추출 링크는 리터럴 인용 필수. 결박 불가 → `status=rejected`.
- **G17 하네스 오프라인**: 외부 지식은 ETL 단계에서만 취득하며 하네스는 해시 고정 스냅샷만 소비.
- **G18 INCONCLUSIVE ≠ PASS**: 증명 불가/상태 캡 초과는 T2 크레딧을 주지 않으며 통과로 취급하지 않는다.
- **G19 렌즈 append-only 및 결측 규칙**: 렌즈 추가는 기존 렌즈·엘리트를 불변으로 두며, 백필은 결정론적. 신규 차원이 결측인 구엔트리는 마스크 거리(공유 차원만)로 처리하고 `imputed=True` 플래그를 남긴다.
- **G20 지평 확장 승인 게이트 (Horizon Admission Test)**: 새 지평 구성요소는 활성화 전 (1) 비활성 시 byte-identical 회귀, (2) 검증 패리티(§0 Law: 크레딧을 주는 영역 ⊆ 검증기가 덮는 영역), (3) 고정 시드 ≥5회 ablation에서 수율 지표 비음(非陰) 개선 — 이를 통과해야 기본값으로 승격. *지평 확장 자체에도 "No Evidence, No Credit"를 적용*.
- **G21 매크로 의미 보존**: 매크로 확장 전/후 oracle 판정(FATAL 집합·T 티어)이 동일하지 않으면 승격 불가.

### 4.3 위험 레지스터

| 위험 | 징후 | 완화 |
|------|------|------|
| 생성 지평만 확대 → 전량 T0 | `operator_yield`≈0, `inconclusive_rate`↑ | V를 R/O/D보다 선행(S4→M1), 티어별 예산 상한 |
| 구조 정크(의미 없는 변이) | 높은 `structural_novelty`, 낮은 `utility` | 게이트 순서 유지(품질 임계), Reskin 후 재평가, 구조신규 AND 의미신규 동시요건 |
| 밴딧 조기 수렴(탐험 기아) | `operator_entropy`↓, `parent_gini`↑ | ε 하한, 디딤돌 부모, 니치 방문수 항 |
| 니치 게이밍 | LLM 라벨 vs 유도값 불일치↑ | G15 (유도 우선) |
| 템플릿 환각 | 인용 가드 위반 | G16, 텍스트 경로는 L2에서 가드 오탐률 측정 후 활성화 |
| 상태 폭발 | `INCONCLUSIVE`↑ | 상태 캡, 증분/심볼릭(L3), 변수 도메인 축소 컴파일 |
| 과적합 적대자(셀프플레이 순환) | 적대자 풀 정체 | 풀 MAP-Elites 다양성 유지, 외부 고정 적대자(기존 3봇)를 회귀 앵커로 영구 유지 |
| 기본 임베딩이 어휘 해시 | 의미 렌즈 무의미 | 의미 렌즈는 실제 임베딩 모델 주입 시에만 활성(`mode` 확인) |

---

## 5. 권고 실행 순서 (의존성 그래프)

```
S1(Ledger) ─┬─> S2(Scheduler) ──────────────┐
            ├─> S4(Exact) ─> M1(DSL v2) ─> M6(attractor) ─> L1(Macro)
            │        └──────> M2(DynamicsV2+Lens) ─> M3(NSLC)
            ├─> S3(JSON 배선) ─> S6(모티프벡터) ─> M4(ETL) ─> L2/L4
            └─> S5(GraphEdit) ──────────────┘          M5(CoRT+Revocation)
```
- **첫 3개 PR 권고**: S1 → S4 → S2. 이유: 측정(S1)이 이후 모든 ablation의 전제, 정확 검증(S4)이 이후 모든 확장의 "안전 여유"를 만들며(P7), 스케줄러(S2)는 계약 변경 없이 `scheduler` 훅만 켜면 되어 ROI가 가장 크다(P8).
- 각 단계 후 Ledger의 `collapse_ratio`, `exact_coverage`, `operator_yield`로 다음 단계 착수 여부를 **데이터로** 결정한다.

## 6. 검증 방법론 (ablation 설계)
- 백엔드: `ScriptedBackend`(Mock은 다양성이 낮아 부적합), 시드 {1..5}, 예산 60슬롯.
- 요인 토글: scheduler{off,on} × exact{off,on} × graph_edit{off,on} × template_pack{22,80+}.
- 종속: `niche_count`, `qd_score`, `collapse_ratio`, `verified_creative_rate`(T1+ 비율), `structural_novelty`, 오류 카운터.
- 판정: 비모수 검정(Mann–Whitney), 효과크기 보고. 회귀 앵커: 비활성 경로의 89 tests + 골든 지문.
