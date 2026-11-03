#!/usr/bin/env bash
set -e

# ==============================================================================
# Minerva Daily QD Research Runner (Track B: CounterField Autonomous Engine)
# ==============================================================================

WORK_DIR="/home/arcturus/hermesWorkspace/projects/CounterField"
DATE_TAG=$(date +"%Y-%m-%d")
TOPIC_DIR="$WORK_DIR/daily_research/$DATE_TAG"

echo "=== [Minerva Daily Research: $DATE_TAG] Starting Track B (CounterField QD Engine) ==="

mkdir -p "$TOPIC_DIR"
cd "$WORK_DIR"

# 1. Verification of upstream baseline
.venv/bin/pytest -q

# 2. Minerva Lead & Backend Execution via minerva launcher
/home/arcturus/.local/bin/minerva --role=lead "$WORK_DIR" "
[Daily Research Cycle: $DATE_TAG]
최종 목표: '초개인화 고성능 아이디어/가설 진화 엔진 (Counterfield QD Engine)' 고도화.

[핵심 가설 탐구 헌법 - 절대 수렴/단일 최적화 금지, 다양성 극대화]
- 최적화된 안전한 가설(클리셰 평균, 뻔한 점진적 개선) 설정을 엄격히 금지합니다.
- Quality-Diversity(QD)의 본질에 따라 '행동 공간의 미개척 니치(Unexplored Niches)'와 '극단적/이질적인 가능성'을 탐구하십시오.
- 기존 주류 시스템의 암묵적 공리를 정면으로 뒤집는 극단적 전복(Invariant Inversion), 물리학/생태학/분산컴퓨팅 등 전혀 다른 도메인의 파격적 동형사상(Isomorphism), 치명적 결함을 역이용하는 변증법적 메커니즘을 적극적으로 발굴하십시오.

오늘의 데일리 연구 태스크:
1. 4대 창의 메커니즘을 바탕으로, 관습적이지 않고 극단적인 새로운 가능성을 열어젖히는 발산적 하위 가설 1건을 선정하십시오.
2. 새로운 인과 템플릿(Causal Template) 또는 파격적 도메인 어댑터 규칙을 설계/보강하십시오.
3. Colab GPU(Tesla T4) 또는 로컬 런타임을 활용해 실제 MAP-Elites 아카이브에 인과 검증을 통과한 높은 참신성(High-Novelty) 후보 메커니즘을 최소 10건 이상 탐색/입적하십시오.
4. 산출물 및 테스트 검증 로그를 $TOPIC_DIR 에 기록하고 1페이지 요약 리포트를 남기십시오.
"

echo "=== [Minerva Daily Research: $DATE_TAG] Completed Successfully ==="
