# ADR-CF-C: 창의성 고도화 엔진 — 4대 메커니즘 수용 설계 청사진

- 상태: Proposed (Specialist 자문안, Karmack TDD 인계 대기)
- 대상: `creative_agent` (3-Contract 모듈식 아키텍처, 44 tests green 기준선)
- 작성 근거: `harness.py / contracts.py / models.py / archive.py / qd.py / evaluator.py / redteam.py / verifier.py / dsl.py / providers.py` 직접 판독 + 실측

---

## 0. 코드 판독으로 확인된 사실 (설계의 전제)

| # | 관찰 | 근거 | 설계 함의 |
|---|------|------|-----------|
| F1 | 하네스는 **탐색(search)이 아니라 샘플링**이다. `generate_candidates(normalized, operator, (), 1)` — context가 항상 `()`, 부모 선택·변이·교배 없음, `config.seed` 미사용 | harness.py:51 | 4대 메커니즘의 공통 선결조건은 "부모/아카이브를 보는 연산자" 도입 |
| F2 | `repair_incubator`는 **쓰기 전용 데드엔드**. `CEGISRepairEngine`은 하네스에서 호출되지 않음 | harness.py, redteam.py:546 | 메커니즘 3의 훅이 이미 존재 → 비용 최저 |
| F3 | 신규성은 **음성 아카이브(클리셰 baseline) 대비**로만 계산. 아카이브 내부 대비 신규성 없음 | evaluator.py:107-113 | 개방형 니치·진짜 "더 창의적"은 측정 불가 → 계측이 선행 |
| F4 | `fingerprint`는 `core_mechanism/affected_system/payoff` **텍스트를 포함**. 라벨만 바꾼 동형 구조는 다른 지문 | models.py:44 | 이종 도메인 투영·재라벨링 우회를 못 잡음 → 구조 지문 별도 필요 |
| F5 | `coverage = len(elites)/36` 하드코딩이나, `_niche_key`는 dynamics가 있으면 `ctx|dyn` 키 → **분모가 이미 틀림**(키 공간 비유계). 실측: Mock 60시도 → 점유 niche 2개 | archive.py:133,22 | NicheSpace 추상화 시 coverage 의미 재정의 필수 |
| F6 | Reservoir 지배는 `(novelty, utility, mechanism_uniqueness)` 3축. surprise/coherence/appropriateness는 지배에 불참 | archive.py:4-7 | 목적 축 추가는 지배 관계 자체를 바꿈 → 버전 관리 필요 |
| F7 | 하네스 `except Exception: continue`, `LLMIdeaProvider.generate`의 예외 시 **Mock으로 조용히 폴백** | harness.py:88, providers.py:273 | 창의 연산자가 조용히 실패·퇴화해도 지표에 안 보임 → 오류 분류 카운터 필수 |
| F8 | 3개 Protocol이 `@runtime_checkable`이고 하네스가 `isinstance(adapter, DomainAdapter)`로 분기 | harness.py:23 | **Protocol에 메서드를 추가하면 기존 서드파티 어댑터가 isinstance에서 탈락**→ 레거시 경로로 오분류. 3계약은 동결해야 함 |
| F9 | `evaluate()`가 내부에서 `provider.canonicalize`를 한 번 더 호출(이중 canonicalize) | evaluator.py:92-95 | 증거 바인딩(candidate_id/fingerprint)과 lineage 검증은 canonical 이후 단일 시점에서만 |

---

## 1. 메커니즘 평가 및 우선순위

평가 축: **레버리지**(비자명 아이디어 증가량) × **구현 가능성**(기존 자산 재사용) × **환각 위험도**(낮을수록 좋음) × **불변식 충돌 위험**.

| 순위 | 메커니즘 | 레버리지 | 구현성 | 환각위험 | 불변식 충돌 | 판정 |
|------|----------|---------|--------|---------|-------------|------|
| **P0.5** | (공통 기반) 계측 + 구조지문 + 연산자 추상화 | 간접(필수) | 높음 | 낮음 | 낮음 | **선행** |
| **1** | **③ 변증법적 반례 통합** | 높음 — 결정론적 오라클이 이미 *반례의 증거*를 제공 | 높음 (`Counterexample`, `replay_counterexample`, `CEGISRepairEngine`, `repair_incubator` 기존재) | 낮음 (재생으로 검증 가능) | 낮음 | **1순위** |
| **2** | **① 고의적 불변식 전복** | 높음 — 생성 분포의 "제거/역전" 지점을 구조적으로 강제 | 중상 (대부분 생성측, 검증은 극성 바인딩 체크) | 중 (불변식 추출이 LLM 의존) | 낮음 | **2순위(①과 병렬 가능)** |
| **3** | **② 이종 도메인 동형 사상** | 최고(진짜 이질성) 이나 **템플릿 라이브러리라는 데이터 자산 비용** | 중 (`networkx` 서브그래프 단형사상으로 검증 가능) | **높음**("유추 연극": 표면 재라벨링) | 중 (구조지문 충돌) | 3순위 — 역할 사상 *증거* 강제 시에만 |
| **4** | **④ 개방형 동적 니치** | 장기적 | 중하 | 낮음 | **높음**(아카이브 원자성·엘리트 비교가능성·coverage 의미 파괴) | **마지막**, 단 "추가만 허용(append-only)" 설계로 |

핵심 판단:
- ③은 **오라클이 이미 가진 부산물(반례)을 창의성 신호로 전환**하는 것이라 한계비용이 가장 낮다. 단, `dsl_program_to_mechanism`은 손실 변환(액션 의존만 요약)이므로 DSL 수리 결과를 그대로 승격하지 말고 **메커니즘 레벨에서 재합성 후 전 파이프라인 재평가**를 거치게 한다.
- ①은 하네스의 `Inversion`/`Removal` 문자열 연산자를 *검증 가능한 연산자*로 승격하는 것. 현재는 프롬프트 한 줄이라 "역전했다고 주장만 해도" 통과한다.
- ②는 레버리지가 가장 크나 가장 쉽게 속는다. **role-map 증거 + 서브그래프 단형사상 검증**이 없으면 도입 금지.
- ④는 인프라 위험이 크므로 `FixedGridSpace`(현행과 바이트 동일 동작) 위에 `CentroidNicheSpace`를 얹는 방식으로 마지막에.

---

## 2. 아키텍처: 3-Contract 보존 + 확장 지점

### ADR-C01. 3개 Protocol은 **동결**, 확장은 *선택적 능력(Capability) Protocol*과 `CreativeOperator`로

- `DomainAdapter / VerificationOracle / BehaviorExtractor`의 메서드 시그니처·집합 불변 (F8).
- 신규 Protocol은 모두 별도 `@runtime_checkable`이며 하네스가 `isinstance`로 **발견**하고 없으면 스킵 → 기존 호출자 0 변경.

```python
# creative_agent/creativity/operators.py
@dataclass(frozen=True)
class OperatorContext:
    problem: NormalizedProblem
    parents: tuple[IdeaCandidate, ...]      # 하네스가 아카이브에서 선택 (F1 해소)
    baselines: NegativeArchive
    archive: "ArchiveView"                   # 읽기 전용 뷰 (insert 불가)
    slot: int
    rng_seed: int                            # = stable_hash(config.seed, slot), 전역 RNG 금지

@runtime_checkable
class CreativeOperator(Protocol):
    name: str
    def propose(self, ctx: OperatorContext) -> list[IdeaCandidate]: ...

class LegacyPromptOperator:                  # 기존 6개 문자열 연산자 래핑 → 기본값, 거동 동일
    def __init__(self, adapter: DomainAdapter, operator: str): ...
```

```python
# 하네스 확장 (모두 키워드 전용, 기본 None = 현행 동작 바이트 동일)
IdeationHarness(adapter, oracle=None, extractor=None, embeddings=None, *,
                operators: Sequence[CreativeOperator] | None = None,
                scheduler: OperatorScheduler | None = None,
                niche_space: NicheSpace | None = None,
                synthesizer: DialecticalSynthesizer | None = None,
                evidence_verifiers: Sequence[LineageVerifier] = ())
```

데이터 흐름(변경분만 굵게):

```
slot ─▶ **scheduler.pick(archive_view)** ─▶ **select_parents(archive)** ─▶ operator.propose(ctx)
      ─▶ adapter.canonicalize_mechanism ─▶ oracle.validate_structure
      ─▶ oracle.evaluate ─▶ **LineageVerifier.verify(candidate)  # 증거 검증, 실패 시 creative credit 박탈(폐기 아님)**
      ─▶ extractor.extract_niche / extract_dynamics ─▶ **niche_space.locate(entry)**
      ─▶ archive.insert(entry, admission)
      ─▶ **REPAIRABLE(RED_TEAM)면 synthesizer.synthesize(entry) → 자식 후보를 같은 루프의 새 슬롯으로 재주입**
```

### ADR-C02. 증거 결속 계보(Evidence-bound Lineage)

`IdeaCandidate`에 선택 필드 `lineage: CreativeLineage | None = None` 추가 (`StrictModel`, `extra=forbid`와 호환, `fingerprint` 계산에서 **제외**).

```python
class InversionEvidence(StrictModel):  kind: Literal["inversion"]; claim_id: str; bound_link_indices: tuple[int,...]; flipped_polarity: bool
class IsomorphismEvidence(StrictModel): kind: Literal["isomorphism"]; template_id: str; role_map: dict[str,str]      # template node -> candidate node
class DialecticEvidence(StrictModel):  kind: Literal["dialectic"]; counterexample_hash: str; parent_fingerprint: str; synthesis_ops: tuple[str,...]
class CreativeLineage(StrictModel):    operator: str; evidence: InversionEvidence | IsomorphismEvidence | DialecticEvidence | None; parent_ids: tuple[str,...]

@runtime_checkable
class LineageVerifier(Protocol):
    def verify(self, candidate: IdeaCandidate, ctx: ...) -> LineageVerdict: ...   # 결정론적, LLM 호출 금지
```

규칙: **LLM이 "역전/유추/통합했다"고 주장해도 `LineageVerdict.verified`가 True일 때만** 창의성 지표·스케줄러 보상·`RuleLibrary` 승격에 반영. 미검증이면 일반 후보로 정상 평가(차단 아님) — 환각을 *막지 않고 무보상*으로 만들어 유인 제거.

`AdmissionStage`에 `PROVENANCE_EVIDENCE = "provenance_evidence"` 추가(문자열 Enum 확장은 호환). 단 **ACCEPTED 판정에는 관여하지 않음**(증거 불량 → 상태 불변, 크레딧만 없음). 게이트 순서(Evaluation Integrity → Structural → Red Team → Quality → Novelty Policy)는 그대로.

---

## 3. 메커니즘별 상세 설계

### 3.1 ③ 변증법적 반례 통합 (1순위)

**목표**: FATAL 반례 → 폐기가 아니라 "규칙 후보"로 승격, 단 재검증 통과 시에만.

```python
# creative_agent/creativity/dialectic.py
class SynthesisProposal(StrictModel):
    child: IdeaCandidate                  # 메커니즘 레벨 재합성 결과 (parent_id=원본.id)
    counterexample: Counterexample
    ops: tuple[str, ...]                  # 예: "add_cost_node", "add_feedback_loop", "invert_roles"

@runtime_checkable
class DialecticalSynthesizer(Protocol):
    def synthesize(self, entry: QDArchiveEntry, counterexamples: tuple[Counterexample,...],
                   rule_library: "RuleLibrary") -> list[SynthesisProposal]: ...
```

- 기본 구현 `CEGISGuidedSynthesizer`: (a) `CEGISRepairEngine`의 결정론적 수리를 **하한선(baseline repair)**으로 계산, (b) LLM 백엔드(`ProposalBackend`, 주입식)가 "이 익스플로잇을 비용·역할·피드백으로 *기능화*하는 규칙"을 `CanonicalMechanism` 수정안으로 제안, (c) 제안 전체를 일반 후보로 **재-canonicalize → validate → evaluate(레드팀 포함)**.
- **SynthesisVerifier(결정론적 4조건, 모두 충족해야 verified)**:
  1. 원 반례 재생: `replay_counterexample(child_program, ce)`가 `reproduced=False`.
  2. **익스플로잇 보존**: witness의 액션 접두열이 자식에서도 `error is None`으로 실행 가능(기능으로 *살아남음* — 단순 삭제/가드 강화로 지운 경우 배제).
  3. **비-미용성**: 자식 `causal_structure`가 부모 대비 **신규 노드 ≥1 이고 신규 링크 ≥2**, 또한 `DynamicalNicheDescriptor`가 `loop_density` 또는 `causal_depth` 증가(=구조적 변화).
  4. **회귀 방지**: 부모가 가졌던 *모든* 반례(`RuleLibrary`의 누적 corpus 포함)를 재생해 미재현.
- 자식은 **정식 후보로서 모든 게이트를 처음부터 통과**해야 아카이브 진입(FATAL 우회 경로 없음). FATAL 부모가 production으로 승격되는 일은 불가능 — 자식만 진입.
- `RuleLibrary`: (반례 클래스 `violated_invariant`, 합성 op 패턴, 성공 횟수). **독립 후보 ≥2건에서 검증 통과해야 "규칙 패턴"으로 승격**(과적합 방지). 승격된 패턴은 `OperatorContext`로 생성기에 컨텍스트 주입(플라이휠).
- 예산: 합성 시도는 `attempts`에 포함, `HarnessConfig.max_synthesis_per_entry`(기본 2)로 상한.

### 3.2 ① 고의적 불변식 전복

```python
class InvariantClaim(StrictModel):
    id: str                               # stable_id(domain, statement)
    statement: str                        # "자원은 많을수록 이득"
    cause: str; relation: Literal[...]; effect: str     # CausalLink와 동일 어휘로 기계화
    evidence_quote: str                   # 문제/베이스라인 텍스트 내 근거 인용 (환각 방지)

@runtime_checkable
class InvariantMiner(Protocol):
    def mine(self, problem: NormalizedProblem, baselines: NegativeArchive) -> tuple[InvariantClaim,...]: ...
```

- **환각 가드**: `evidence_quote`가 `problem.original_prompt` 또는 baseline 텍스트(NFKC·casefold 정규화 후)의 **부분 문자열**이어야 claim 유효. 근거 없는 공리는 폐기.
- `InversionOperator.propose`: claim을 골라 "relation 극성 반전 + 붕괴 완충 메커니즘 포함"을 요구. 후보는 `InversionEvidence(bound_link_indices=...)`를 반드시 제출.
- **InversionVerifier**: (i) bound 링크가 후보 `causal_structure`에 실존, (ii) 해당 (cause,effect) 쌍에서 claim 대비 **극성 반대**(`increases↔decreases`, `enables↔prevents`), (iii) 반전으로 생기는 붕괴 경로를 막는 **완충 경로 ≥1**: 반전 링크의 effect에서 payoff까지의 경로가 존재하되 반전 링크를 우회하는 경로이거나 새 노드를 경유(그래프 검증은 `CausalGraphValidator.build_graph` 재사용). 반전만 하고 payoff 도달성이 없으면 이미 `payoff_reachability` FATAL로 탈락(기존 게이트가 자연스럽게 방어).
- 연산자 스케줄: claim당 "단일 반전"→성공 시 "이중 반전(두 공리 동시)" 순으로 난이도 상승(커리큘럼).

### 3.3 ② 이종 도메인 동형 사상

```python
class CausalTemplate(StrictModel):
    id: str; domain: str                  # "ecology", "os_kernel", "thermodynamics", "auction"
    roles: tuple[str,...]                 # 추상 역할 노드
    links: tuple[CausalLink,...]          # 역할 기반 인과 (relation 보존)
    motifs: tuple[Literal["feedback_loop","bottleneck","asymmetry",...],...]
    curated_by: str; source_ref: str      # 출처 필수 (환각 템플릿 금지)

class TemplateLibrary(Protocol):
    def match(self, motifs: "MotifProfile", k: int) -> tuple[CausalTemplate,...]: ...
```

- `MotifExtractor`: 문제/베이스라인 그래프에서 피드백 루프(SCC>1), 병목(articulation/최대 betweenness), 비대칭(in/out degree 비) → `MotifProfile`. `networkx`만 사용, 결정론적.
- **IsomorphismVerifier**: 후보의 role_map이 (a) **단사**, (b) 템플릿의 *모든* 링크를 후보 그래프에서 **relation 보존 단형사상**(`DiGraphMatcher.subgraph_is_monomorphic`, edge match=relation)으로 포함, (c) 매핑된 후보 노드 라벨이 템플릿 역할명/도메인 어휘를 그대로 복사한 게 아니라 문제 도메인 어휘임(템플릿 `domain` 어휘 blacklist 토큰 교집합 검사).
- **"표면 재라벨링" 방어**: 후보 구조가 *문제 도메인 baseline의 구조지문과 이미 동형*이면(§4 G4) 증거 무효.
- 라이브러리는 **큐레이션 자산**이며 초기 4도메인×3템플릿(총 12)에서 시작. LLM이 즉석 생성한 템플릿은 `curated_by="llm"`이면 `source_ref` 없이는 `match` 후보에서 제외.

### 3.4 ④ 개방형 동적 니치

핵심 원칙: **비지도 클러스터링으로 키를 재배정하지 않는다** (키 불안정 → 엘리트 무효화, 비결정성). 대신 **append-only CVT 센트로이드**.

```python
@runtime_checkable
class NicheSpace(Protocol):
    version: int
    def locate(self, entry: QDArchiveEntry) -> str: ...              # niche_key
    def maybe_expand(self, entries: Sequence[QDArchiveEntry], rng_seed: int) -> "NicheSpaceDelta": ...
    @property
    def capacity(self) -> int | None: ...                            # 고정 그리드면 36, 개방형이면 None

class FixedGridSpace:       # 현행 로직 그대로 (회귀 기준선, 기본값)
class CentroidNicheSpace:   # 행동 벡터 = (ctx one-hot, causal_depth, branching, loop_density, payoff_len) 정규화
```

- 확장 규칙(Novelty-Search 임계): 기존 센트로이드 중 최근접까지의 거리 > `ρ`인 ACCEPTED 엔트리가 `m`개 이상 누적되면 **그 군집 중심을 새 센트로이드로 추가**. 기존 센트로이드·할당은 **불변**(재할당 없음 → 엘리트 불변, 단조성).
- 센트로이드 추가는 **아카이브 트랜잭션 안에서**(snapshot/restore에 `niche_space` 상태 포함). 실패 시 동시 롤백.
- coverage 재정의: `coverage = occupied / capacity` (capacity=None이면 `None` 반환하고 `niche_count`, `qd_score`(엘리트 스칼라 품질 합, *지표 전용*), `novelty_archive_size`로 대체). `/36` 하드코딩 제거(F5).
- Novelty 보강: `archive_relative_novelty` = 행동 벡터 기준 아카이브 k-NN 평균 거리. **`EvaluationScores`/지배 판정에는 넣지 않고** `EvaluationDiagnostics`/`metrics`에만 노출(F6 보호).

---

## 4. 불변식 가드레일 (Shift-Left Invariant Guard)

| ID | 불변식 | 위반 시나리오 | 강제 방법 |
|----|--------|---------------|-----------|
| **G1** 단일 문 | ACCEPTED만 production(elites/reservoir)에 진입. 합성 자식·역전·유추 후보도 예외 없음 | FATAL 반례 후보를 "규칙으로 승격"하며 부모를 아카이브에 넣음 | `archive.insert`의 기존 FATAL→REPAIRABLE 강등 유지 + **부모 id는 production 불가** 테스트 |
| **G2** 증거는 무보상 원칙 | `lineage.evidence` 미검증이면 창의성 지표·스케줄 보상 0, 그러나 후보 평가는 정상 | 환각 유추가 "창의적"으로 계수됨 | `LineageVerdict.verified` 게이트, 지표는 verified만 집계 |
| **G3** 지문 동결 | `CanonicalMechanism.fingerprint` 산식·NFKC·`\|` 이스케이프 **변경 금지**. lineage/provenance는 지문 제외 | 필드 추가로 기존 id 전부 변동 | 골든 지문 테스트(고정 벡터 해시 고정) |
| **G4** 구조 지문 병설 | `structural_fingerprint` = 노드 라벨 소거 + relation 보존 WL-hash (`networkx.weisfeiler_lehman_graph_hash`). 신규 필드/함수로만 추가 | 재라벨링 동형 후보가 신규로 오인 | 노드 수 ≥4 일 때만 baseline 동형 → `NOVELTY_POLICY` REJECTED(소형 체인은 우연 동형 다수라 제외) |
| **G5** 아카이브 원자성 | 센트로이드 추가, RuleLibrary 갱신, admission_log가 한 트랜잭션. 중간 예외 시 전부 복원 | niche 증설 후 insert 실패 → 고아 센트로이드 | `_snapshot/_restore`에 `niche_space`, `rule_library` 포함 + 예외 주입 테스트 |
| **G6** 파레토 보존 | 지배 목적 축은 `(novelty, utility, mechanism_uniqueness)` 유지. 축 변경 시 `dominance_version` 증가 + reservoir 일괄 재계산 트랜잭션 | 신규 축 도입으로 기존 reservoir가 비일관 | 기본 유지, 축 추가는 별도 ADR + 마이그레이션 테스트 |
| **G7** 엘리트 단조성 | 니치 확장은 기존 엘리트를 퇴출하지 않음. 타이브레이크 `id <`는 결정론 유지 | 재군집으로 엘리트 소실 | append-only 센트로이드, 사전/사후 elites ⊆ 검증 |
| **G8** 결정론 | 모든 연산자 RNG는 `stable_id(seed, slot, op)` 파생. 전역 `random` 금지. 같은 seed → 같은 archive | 재현 불가 | 동일 seed 2회 실행 `admission_log` 동일 테스트 |
| **G9** 제로 네트워크 | 모든 신규 연산자는 주입식 `ProposalBackend`(LLM)와 `ScriptedBackend`(테스트) 분리. 검증기는 **LLM 호출 금지** | 검증이 LLM 판단에 의존 → 환각 승인 | 검증기 모듈에서 네트워크 import 금지 테스트(정적) |
| **G10** 침묵 실패 금지 | `except Exception: continue`를 오류 분류 카운터(`generation_errors`, `canonicalize_errors`, `evidence_errors`, `provider_fallbacks`)로 치환. LLM→Mock 폴백은 `provenance.provider_mode="mock-fallback"` 표기 | 창의 연산자가 퇴화해도 모름 | 폴백 시 메트릭 증가 + 폴백 후보는 creative credit 불가 |
| **G11** 예산 | 합성/증거검증/템플릿 매칭 호출도 `budget`에 계상. 연산자별 상한 | 합성 폭주로 예산 소진 | `attempts` 계상 + 상한 테스트 |
| **G12** 자기참조 방지 | 합성 깊이 상한(`lineage` 체인 ≤3), 동일 `counterexample_hash` 재합성 금지 | 무한 수리-재파손 루프 | 깊이/해시 중복 가드 |

"엉터리 메커니즘" 최소 방어선 요약: **(1) 구조 게이트(기존) → (2) 레드팀 FATAL 격리(기존) → (3) 증거 결속·결정론 검증(신규) → (4) 증거 없으면 무보상**. 신규 코드는 기존 게이트를 *우회하는 경로를 만들지 않고*, 앞단에서 후보의 *질*을 올리는 방식으로만 개입한다.

---

## 5. 창의성 계측 (먼저 만들고, 그 뒤 연산자를 켠다)

`creative_agent/creativity/metrics.py` — 모두 `HarnessResult.metrics`에 추가(기존 키 유지):

- `verified_creative_rate` = verified lineage ACCEPTED / ACCEPTED
- `structural_novelty` = 후보 구조지문의 아카이브·baseline 대비 최소 거리 평균
- `operator_yield[name]` = {attempts, accepted, verified, new_niches, reservoir_inserts}
- `synthesis_conversion` = FATAL → 검증된 자식 ACCEPTED 비율
- `qd_score`, `niche_count`, `capacity`, `structural_duplicate_rate`
- 에러 카운터(G10)

**애블레이션 규약**: 동일 seed·동일 `ScriptedBackend`로 `LegacyPromptOperator`만 vs +각 연산자. 성공 기준 = `verified_creative_rate`·`structural_novelty` 상승 **and** G1~G12 전부 green **and** 기존 44 테스트 무수정 통과.

---

## 6. 단계별 로드맵 (Karmack TDD 인계)

각 Phase는 독립 머지 가능, 직전 Phase green이 다음의 입장 조건.

### Phase 0 — 기반 (연산자 추상화 + 계측 + 구조지문) · 선행
모듈: `creativity/operators.py`, `creativity/structure.py`, `creativity/metrics.py`, `harness.py`(키워드 전용 인자), `models.py`(`lineage` 선택 필드), `archive.py`(`capacity` 인지 coverage는 Phase 4에서)
테스트(RED 먼저):
1. `test_default_harness_is_byte_identical`: operators=None일 때 `admission_log`·metrics가 변경 전 골든과 동일.
2. `test_fingerprint_golden_vectors_unchanged` (G3).
3. `test_lineage_excluded_from_fingerprint`.
4. `test_structural_fingerprint_label_invariant`: 라벨 치환 → 동일, relation 하나 변경 → 상이.
5. `test_structural_fingerprint_small_graph_not_blacklisted` (노드<4).
6. `test_legacy_operator_matches_round_robin_order`.
7. `test_operator_rng_deterministic_by_seed` (G8).
8. `test_generation_error_counters_not_silent` / `test_llm_fallback_marked_and_uncredited` (G10).
9. `test_existing_protocols_unchanged`: 3 Protocol의 멤버 집합이 정확히 현행과 동일(F8 회귀 방어).
10. `test_parent_selection_feeds_context`: 하네스가 비어있지 않은 `parents`를 연산자에 전달.

### Phase 1 — ③ 변증법적 통합
모듈: `creativity/dialectic.py`, `creativity/lineage.py`(DialecticEvidence + verifier), `RuleLibrary`
테스트:
1. `test_fatal_parent_never_enters_production` (G1).
2. `test_child_must_replay_clean_but_preserve_witness_prefix`: 가드 강화로 단순 삭제한 자식 → 비검증.
3. `test_cosmetic_synthesis_rejected` (신규 노드 0 / 링크 <2 → 무보상).
4. `test_regression_corpus_replayed` (부모의 다른 반례 재현 시 비검증).
5. `test_rule_promotion_requires_two_independent_successes`.
6. `test_synthesis_budget_and_depth_cap` (G11,G12).
7. `test_synthesis_atomic_rollback_on_insert_failure` (G5).
8. `test_repair_incubator_consumed_when_synthesizer_present`, `..._untouched_when_absent`.
9. 속성 기반(Hypothesis): 임의 반례에 대해 verified child는 항상 모든 게이트 통과.

### Phase 2 — ① 불변식 전복
모듈: `creativity/inversion.py` (`InvariantClaim/Miner`, `InversionOperator`, `InversionVerifier`)
테스트:
1. `test_claim_without_prompt_evidence_quote_dropped` (NFKC/casefold 포함, 한/영).
2. `test_polarity_flip_detected` 5개 relation 쌍 전수.
3. `test_inversion_without_buffer_path_unverified_or_fatal`.
4. `test_unbound_link_indices_unverified`.
5. `test_inversion_curriculum_single_then_double`.
6. `test_unverified_inversion_gets_no_scheduler_reward` (G2).

### Phase 3 — ② 이종 도메인 동형
모듈: `creativity/isomorphism.py`, `creativity/templates/*.json`(큐레이션 12개), `MotifExtractor`, `BlendOperator`, `IsomorphismVerifier`
테스트:
1. `test_motif_extraction_feedback_bottleneck_asymmetry` (고정 그래프 골든).
2. `test_role_map_must_be_injective`.
3. `test_relation_preserving_monomorphism_required` (relation 불일치 시 비검증).
4. `test_template_vocabulary_copy_rejected` (표면 복사).
5. `test_isomorphic_to_baseline_is_not_credited` (G4).
6. `test_template_without_source_ref_excluded`.
7. `test_blend_runs_zero_network_with_scripted_backend` (G9).

### Phase 4 — ④ 개방형 니치
모듈: `creativity/niche_space.py`, `archive.py` 최소 수정(`niche_space` 주입, snapshot 포함, coverage 일반화)
테스트:
1. `test_fixed_grid_space_equals_legacy_keys` (회귀).
2. `test_centroid_expansion_is_append_only_and_elites_monotone` (G7).
3. `test_expansion_rolled_back_with_failed_insert` (G5).
4. `test_expansion_deterministic_by_seed` (G8).
5. `test_coverage_none_for_open_space_and_metrics_present`.
6. `test_reservoir_independent_of_niche_space` (G6): 니치 확장이 reservoir 구성을 바꾸지 않음.
7. `test_below_rho_does_not_expand`.

### Phase 5 — 통합·스케줄러·벤치
`OperatorScheduler`(UCB 결정론, 보상 = verified 신규 니치/reservoir 삽입), 애블레이션 벤치 스크립트, CLI 플래그(`--operators`, 기본 legacy). 통합 테스트: 4개 연산자 동시 활성 시 G1~G12 불변식 스위프.

---

## 7. 리스크·오픈 이슈

1. **LLM 백엔드 품질**: ①③의 상한은 `ProposalBackend` 품질이 결정. 검증기가 결정론이라 *품질 저하 = 무보상*으로 안전하게 퇴화하지만 효과도 0. → 애블레이션으로 상시 모니터.
2. **DSL 컴파일의 의미 손실**: `mechanism_to_semantic_ir`가 인과 링크를 상태기계로 옮길 때 창의 구조(새 노드)가 반영되는지 Phase 1 착수 전 스파이크 필요(합성 자식의 신규 노드가 실제로 DSL에 상태/액션으로 나타나야 레드팀이 의미 있음).
3. **템플릿 큐레이션 비용**(②): 사람 검수 필수. 초기엔 소수정예.
4. **Mock 제공자의 다양성 한계**: 실측 Mock 60시도 → niche 2개. 신규 테스트는 `ScriptedBackend` 고정 시나리오 사용(Mock 의존 금지).
5. **EvaluationScores의 LLM 의존(`provider.assess`)**: utility/surprise 자체가 LLM 판단 → 지배 판정의 한 축이 비결정적. 본 ADR 범위 밖이나 후속 ADR 권고.
6. **문서 라우팅**: 본 문서는 프로젝트 `docs/`에 위치. 영구 설계 기록 SoT는 Vault(`01_PROJECTS/Counterfield`)이므로 Kondo로 동기화 필요(미실시).
