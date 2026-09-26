"""Deterministic adversarial playtesting for declarative mechanisms.

The bots operate through :class:`StateMachineSimulator`; they never evaluate
code embedded in a mechanism.  Every reported problem includes an action
sequence that can be replayed against the same program.
"""

from __future__ import annotations

import random
from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .dsl import (
    DSLAction,
    DSLProgram,
    GuardCondition,
    Scalar,
    SimulationTrace,
    StateEffect,
    StateMachineSimulator,
    StateVariable,
    TerminalCondition,
    canonical_mechanism_to_dsl,
)
from .models import (
    CanonicalMechanism,
    Counterexample,
    PlaytestIssue,
    PlaytestReport,
    RepairOperator,
    StrictModel,
)


def _state_key(state: Mapping[str, Scalar]) -> tuple[tuple[str, Scalar], ...]:
    return tuple(sorted(state.items()))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class _BotRun:
    issues: tuple[PlaytestIssue, ...]
    metrics: dict[str, Any]


class ExploitBot:
    """Search for fixed-action wins and direct payoff shortcuts."""

    name = "ExploitBot"

    def run(self, program: DSLProgram) -> _BotRun:
        simulator = StateMachineSimulator(program)
        spam_witnesses: dict[str, tuple[str, ...]] = {}
        issues: list[PlaytestIssue] = []

        for action in program.actions:
            witness = self._spam_to_win(simulator, action)
            # A single legitimate transition is not "spam".  The exploit is
            # specifically repeated use of one action to collapse progression.
            if witness is None or len(witness) < 2:
                continue
            spam_witnesses[action.name] = witness
            issues.append(PlaytestIssue(
                severity="FATAL",
                bot_name=self.name,
                issue_type="single_action_spam",
                description=(
                    f"Repeating only '{action.name}' reaches the win payoff in "
                    f"{len(witness)} step(s)."
                ),
                witness_actions=witness,
            ))

        shortcut = self._find_direct_shortcut(simulator)
        if shortcut is not None:
            final_action = shortcut[-1]
            # A one-action spam witness already describes exactly the same flaw.
            if not (len(shortcut) == 1 and final_action in spam_witnesses):
                issues.append(PlaytestIssue(
                    severity="FATAL",
                    bot_name=self.name,
                    issue_type="payoff_shortcut",
                    description=(
                        f"Action '{final_action}' directly sets a payoff state and "
                        "bypasses the program's staged progression."
                    ),
                    witness_actions=shortcut,
                ))

        metrics = {
            "exploit_detected": bool(issues),
            "spam_actions_tested": len(program.actions),
            "spam_wins": {name: list(path) for name, path in spam_witnesses.items()},
            "shortcut_witness": list(shortcut) if shortcut is not None else None,
        }
        return _BotRun(tuple(issues), metrics)

    @staticmethod
    def _spam_to_win(
        simulator: StateMachineSimulator, action: DSLAction
    ) -> tuple[str, ...] | None:
        state = simulator.initial_state()
        if simulator.terminal_outcome(state) is not None:
            return None
        witness: list[str] = []
        for _ in range(simulator.program.max_steps):
            if action not in simulator.available_actions(state):
                return None
            state = simulator.transition(state, action)
            witness.append(action.name)
            outcome = simulator.terminal_outcome(state)
            if outcome == "win":
                return tuple(witness)
            if outcome == "loss":
                return None
        return None

    @staticmethod
    def _find_direct_shortcut(simulator: StateMachineSimulator) -> tuple[str, ...] | None:
        """Find a short path ending in an unguarded direct payoff assignment.

        Direct assignments are not inherently exploits.  They are suspicious
        when the winning path uses fewer actions than the mechanism defines and
        the final action does not guard the payoff variable it overwrites.
        """

        program = simulator.program
        payoff_vars = {
            guard.var_name
            for terminal in program.terminal_conditions
            if terminal.outcome == "win"
            for guard in terminal.guards
        }
        if len(program.actions) < 2 or not payoff_vars:
            return None

        initial = simulator.initial_state()
        queue = deque([(initial, ())])
        seen = {_state_key(initial)}
        search_limit = min(program.max_steps, max(2, len(program.actions)))
        state_limit = 5_000

        while queue and len(seen) <= state_limit:
            state, path = queue.popleft()
            if len(path) >= search_limit:
                continue
            for action in simulator.available_actions(state):
                successor = simulator.transition(state, action)
                next_path = (*path, action.name)
                if simulator.terminal_outcome(successor) == "win":
                    direct_payoff_vars = {
                        effect.var_name
                        for effect in action.effects
                        if effect.op == "set" and effect.var_name in payoff_vars
                    }
                    guarded_vars = {guard.var_name for guard in action.guards}
                    if (
                        direct_payoff_vars - guarded_vars
                        and len(next_path) < len(program.actions)
                    ):
                        return next_path
                    continue
                key = _state_key(successor)
                if key not in seen:
                    seen.add(key)
                    queue.append((successor, next_path))
        return None


class FatigueBot:
    """Measure repetitive input, state cycles, and payoff trajectory bloat."""

    name = "FatigueBot"

    def __init__(self, *, warning_threshold: float = 0.6, fatal_threshold: float = 0.75):
        if not 0 <= warning_threshold <= fatal_threshold <= 1:
            raise ValueError("fatigue thresholds must satisfy 0 <= warning <= fatal <= 1")
        self.warning_threshold = warning_threshold
        self.fatal_threshold = fatal_threshold

    def run(self, program: DSLProgram) -> _BotRun:
        simulator = StateMachineSimulator(program)
        traces = [
            simulator.run(policy="payoff-seeking", seed=0),
            simulator.run(policy="first", seed=0),
            *(simulator.run(policy="random", seed=seed) for seed in range(8)),
        ]
        winning_lengths = [trace.steps_taken for trace in traces if trace.outcome == "win"]
        observed_shortest_payoff = min(winning_lengths) if winning_lengths else None
        analyses = [
            self._analyze(trace, program.max_steps, observed_shortest_payoff)
            for trace in traces
        ]
        worst_index = max(range(len(analyses)), key=lambda index: analyses[index]["fatigue_score"])
        metrics = analyses[worst_index]
        trace = traces[worst_index]
        score = metrics["fatigue_score"]
        issues: list[PlaytestIssue] = []

        if metrics["non_evolving_steps"] > 0 or metrics["cycle_length"] is not None:
            if trace.outcome == "timeout" or metrics["meaningful_state_ratio"] < 0.5:
                issues.append(PlaytestIssue(
                    severity="FATAL" if score >= self.fatal_threshold else "WARNING",
                    bot_name=self.name,
                    issue_type="non_evolving_loop",
                    description=(
                        "The trajectory repeats states or actions without meaningful "
                        "state evolution."
                    ),
                    witness_actions=tuple(step.action for step in trace.trajectory),
                ))

        if score >= self.warning_threshold:
            issues.append(PlaytestIssue(
                severity="FATAL" if score >= self.fatal_threshold else "WARNING",
                bot_name=self.name,
                issue_type="repetitive_grind",
                description=(
                    f"The worst trajectory has fatigue score {score:.3f}, with "
                    f"{metrics['repeated_action_ratio']:.1%} repeated actions."
                ),
                witness_actions=tuple(step.action for step in trace.trajectory),
            ))

        metrics = {
            **metrics,
            "trajectory_outcome": trace.outcome,
            "witness_actions": [step.action for step in trace.trajectory],
            "traces_analyzed": len(traces),
        }
        return _BotRun(tuple(issues), metrics)

    @staticmethod
    def _analyze(
        trace: SimulationTrace,
        max_steps: int,
        observed_shortest_payoff: int | None = None,
    ) -> dict[str, Any]:
        actions = [step.action for step in trace.trajectory]
        length = len(actions)
        if length == 0:
            return {
                "fatigue_score": 0.0,
                "action_repetition": 0.0,
                "repeated_action_ratio": 0.0,
                "consecutive_repeat_ratio": 0.0,
                "cycle_length": None,
                "trajectory_bloat": 0.0,
                "observed_shortest_payoff": observed_shortest_payoff,
                "meaningful_state_ratio": 1.0,
                "non_evolving_steps": 0,
                "steps_before_payoff": 0,
            }

        counts = Counter(actions)
        action_repetition = max(counts.values()) / length
        repeated_action_ratio = (length - len(counts)) / length
        consecutive = sum(a == b for a, b in zip(actions, actions[1:]))
        consecutive_ratio = consecutive / max(1, length - 1)

        states = [trace.trajectory[0].state_before]
        states.extend(step.state_after for step in trace.trajectory)
        first_seen: dict[tuple[tuple[str, Scalar], ...], int] = {}
        cycle_lengths: list[int] = []
        for index, state in enumerate(states):
            key = _state_key(state)
            if key in first_seen:
                cycle_lengths.append(index - first_seen[key])
            else:
                first_seen[key] = index

        non_evolving = sum(step.state_before == step.state_after for step in trace.trajectory)
        meaningful_ratio = (length - non_evolving) / length
        if observed_shortest_payoff is not None:
            trajectory_bloat = max(0.0, (length - observed_shortest_payoff) / length)
        elif trace.outcome == "timeout":
            trajectory_bloat = length / max_steps
        else:
            trajectory_bloat = 0.0
        duration_pressure = _clamp01((length - 5) / max(5, max_steps - 5))
        loop_pressure = max(
            non_evolving / length,
            1.0 if cycle_lengths and trace.outcome == "timeout" else 0.0,
        )
        fatigue = _clamp01(
            0.35 * repeated_action_ratio
            + 0.25 * consecutive_ratio
            + 0.20 * loop_pressure
            + 0.20 * duration_pressure
            + 0.10 * trajectory_bloat
        )
        return {
            "fatigue_score": round(fatigue, 6),
            "action_repetition": round(action_repetition, 6),
            "repeated_action_ratio": round(repeated_action_ratio, 6),
            "consecutive_repeat_ratio": round(consecutive_ratio, 6),
            "cycle_length": min(cycle_lengths) if cycle_lengths else None,
            "trajectory_bloat": round(trajectory_bloat, 6),
            "observed_shortest_payoff": observed_shortest_payoff,
            "meaningful_state_ratio": round(meaningful_ratio, 6),
            "non_evolving_steps": non_evolving,
            "steps_before_payoff": length,
        }


class ChaosBot:
    """Fuzz valid action sequences and stress state invariants."""

    name = "ChaosBot"

    def __init__(self, *, episodes: int = 64, seed: int = 0):
        if episodes <= 0:
            raise ValueError("episodes must be greater than zero")
        self.episodes = episodes
        self.seed = seed

    def run(self, program: DSLProgram) -> _BotRun:
        simulator = StateMachineSimulator(program)
        rng = random.Random(self.seed)
        crashes: list[tuple[tuple[str, ...], str]] = []
        invariant_failures: list[tuple[str, ...]] = []
        stuck_witnesses: list[tuple[str, ...]] = []
        outcomes: Counter[str] = Counter()
        action_coverage: set[str] = set()

        for _ in range(self.episodes):
            selected: list[str] = []

            def chaotic_policy(_state, available):
                action = rng.choice(available)
                selected.append(action.name)
                return action

            try:
                trace = simulator.run(policy=chaotic_policy)
                outcomes[trace.outcome] += 1
                witness = tuple(step.action for step in trace.trajectory)
                action_coverage.update(witness)
                if trace.outcome == "stuck":
                    stuck_witnesses.append(witness)
                if not trace.active_invariants_preserved or any(
                    not self._state_in_bounds(program, step.state_after)
                    for step in trace.trajectory
                ):
                    invariant_failures.append(witness)
            except Exception as exc:  # A fuzzer must convert transition failures into evidence.
                crashes.append((tuple(selected), f"{type(exc).__name__}: {exc}"))

        issues: list[PlaytestIssue] = []
        if crashes:
            witness, error = min(crashes, key=lambda item: len(item[0]))
            issues.append(PlaytestIssue(
                severity="FATAL",
                bot_name=self.name,
                issue_type="transition_crash",
                description=f"A valid chaotic transition crashed: {error}",
                witness_actions=witness,
            ))
        if invariant_failures:
            witness = min(invariant_failures, key=len)
            issues.append(PlaytestIssue(
                severity="FATAL",
                bot_name=self.name,
                issue_type="broken_invariant",
                description="A chaotic trajectory produced an out-of-bounds or invalid state.",
                witness_actions=witness,
            ))
        if stuck_witnesses:
            witness = min(stuck_witnesses, key=len)
            issues.append(PlaytestIssue(
                severity="FATAL" if len(stuck_witnesses) == self.episodes else "WARNING",
                bot_name=self.name,
                issue_type="reachable_stuck_state",
                description=(
                    f"{len(stuck_witnesses)} of {self.episodes} chaotic episodes "
                    "reached a non-terminal state with no valid action."
                ),
                witness_actions=witness,
            ))

        failed_episodes = len(crashes) + len(invariant_failures) + len(stuck_witnesses)
        robustness = _clamp01(1.0 - failed_episodes / self.episodes)
        metrics = {
            "robustness_score": round(robustness, 6),
            "episodes": self.episodes,
            "seed": self.seed,
            "outcomes": dict(outcomes),
            "crashes": len(crashes),
            "invariant_failures": len(invariant_failures),
            "stuck_episodes": len(stuck_witnesses),
            "action_coverage": sorted(action_coverage),
            "action_coverage_ratio": round(len(action_coverage) / max(1, len(program.actions)), 6),
        }
        return _BotRun(tuple(issues), metrics)

    @staticmethod
    def _state_in_bounds(program: DSLProgram, state: Mapping[str, Scalar]) -> bool:
        if set(state) != set(program.states):
            return False
        for name, variable in program.states.items():
            value = state[name]
            if variable.var_type == "int" and (not isinstance(value, int) or isinstance(value, bool)):
                return False
            if variable.var_type == "float" and (
                not isinstance(value, (int, float)) or isinstance(value, bool)
            ):
                return False
            if variable.var_type == "bool" and not isinstance(value, bool):
                return False
            if variable.var_type == "enum" and not isinstance(value, str):
                return False
            if variable.min_val is not None and value < variable.min_val:
                return False
            if variable.max_val is not None and value > variable.max_val:
                return False
        return True


class AdversarialPlaytester:
    """Run the complete red-team suite and aggregate structured telemetry."""

    def __init__(self, *, chaos_episodes: int = 64, seed: int = 0):
        self.exploit_bot = ExploitBot()
        self.fatigue_bot = FatigueBot()
        self.chaos_bot = ChaosBot(episodes=chaos_episodes, seed=seed)

    def run_playtest(self, program: DSLProgram | CanonicalMechanism) -> PlaytestReport:
        if isinstance(program, CanonicalMechanism):
            program = canonical_mechanism_to_dsl(program)
        if not isinstance(program, DSLProgram):
            raise TypeError("program must be a DSLProgram or CanonicalMechanism")

        exploit = self.exploit_bot.run(program)
        fatigue = self.fatigue_bot.run(program)
        chaos = self.chaos_bot.run(program)
        issues = [*exploit.issues, *fatigue.issues, *chaos.issues]
        return PlaytestReport(
            is_passed=not any(issue.severity == "FATAL" for issue in issues),
            exploit_detected=bool(exploit.metrics["exploit_detected"]),
            fatigue_score=float(fatigue.metrics["fatigue_score"]),
            robustness_score=float(chaos.metrics["robustness_score"]),
            issues=issues,
            bot_results={
                self.exploit_bot.name: exploit.metrics,
                self.fatigue_bot.name: fatigue.metrics,
                self.chaos_bot.name: chaos.metrics,
            },
        )


class CounterexampleReplay(StrictModel):
    reproduced: bool
    outcome: str
    final_state: dict[str, Scalar]
    error: str | None = None


class RepairStep(StrictModel):
    operator: RepairOperator
    counterexample: Counterexample
    witness_reproduced: bool


class RepairResult(StrictModel):
    program: DSLProgram
    healed: bool
    steps: tuple[RepairStep, ...]
    remaining_counterexamples: tuple[Counterexample, ...]
    playtest_report: PlaytestReport


def counterexamples_from_report(
    report: PlaytestReport, program: DSLProgram
) -> tuple[Counterexample, ...]:
    initial_state = StateMachineSimulator(program).initial_state()
    return tuple(
        Counterexample(
            witness_actions=issue.witness_actions,
            initial_state=initial_state,
            violated_invariant=issue.issue_type,
        )
        for issue in report.issues
        if issue.severity == "FATAL"
    )


def replay_counterexample(
    program: DSLProgram, counterexample: Counterexample
) -> CounterexampleReplay:
    """Replay exactly the captured witness and classify the original invariant."""
    simulator = StateMachineSimulator(program)
    state = dict(counterexample.initial_state)
    if set(state) != set(program.states):
        # A repair may add bookkeeping state.  Preserve the captured values and
        # initialize only the newly introduced variables.
        state = simulator.initial_state() | {
            key: value for key, value in state.items() if key in program.states
        }
    states = [dict(state)]
    error = None
    try:
        for action_name in counterexample.witness_actions:
            state = simulator.transition(state, action_name)
            states.append(dict(state))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    outcome = simulator.terminal_outcome(state) if error is None else None
    invariant = counterexample.violated_invariant
    if invariant in {"single_action_spam", "payoff_shortcut"}:
        reproduced = outcome == "win"
    elif invariant == "transition_crash":
        reproduced = error is not None and "unknown action" not in error
    elif invariant == "broken_invariant":
        reproduced = error is not None
    elif invariant == "reachable_stuck_state":
        reproduced = (
            error is None
            and outcome is None
            and not simulator.available_actions(state)
        )
    elif invariant in {"non_evolving_loop", "repetitive_grind"}:
        repeated_states = len({_state_key(item) for item in states}) < len(states)
        repeated_actions = len(set(counterexample.witness_actions)) < len(
            counterexample.witness_actions
        )
        reproduced = error is None and outcome != "win" and (
            repeated_states or repeated_actions
        )
    else:
        reproduced = error is not None or outcome == "win"
    return CounterexampleReplay(
        reproduced=reproduced,
        outcome=outcome or ("error" if error else "non_terminal"),
        final_state=state,
        error=error,
    )


class CEGISRepairEngine:
    """Counterexample-guided repair with typed, deterministic operators."""

    def __init__(self, *, max_iterations: int = 8, chaos_episodes: int = 32, seed: int = 0):
        if max_iterations <= 0:
            raise ValueError("max_iterations must be greater than zero")
        self.max_iterations = max_iterations
        self.playtester = AdversarialPlaytester(
            chaos_episodes=chaos_episodes,
            seed=seed,
        )

    def heal(
        self,
        program: DSLProgram,
        counterexamples: tuple[Counterexample, ...] | None = None,
    ) -> RepairResult:
        current = program
        report = self.playtester.run_playtest(current)
        active = counterexamples or counterexamples_from_report(report, current)
        steps: list[RepairStep] = []

        for iteration in range(self.max_iterations):
            if not active:
                break
            counterexample = active[0]
            operator = self._select_operator(counterexample, iteration)
            repaired = self.apply_operator(current, counterexample, operator)
            replay = replay_counterexample(repaired, counterexample)
            steps.append(RepairStep(
                operator=operator,
                counterexample=counterexample,
                witness_reproduced=replay.reproduced,
            ))
            current = repaired
            report = self.playtester.run_playtest(current)
            active = counterexamples_from_report(report, current)
            if report.is_passed:
                active = ()
                break

        return RepairResult(
            program=current,
            healed=report.is_passed and not active,
            steps=tuple(steps),
            remaining_counterexamples=tuple(active),
            playtest_report=report,
        )

    @staticmethod
    def _select_operator(counterexample: Counterexample, iteration: int) -> RepairOperator:
        invariant = counterexample.violated_invariant
        if invariant == "single_action_spam":
            return RepairOperator.SPLIT_TRANSITION
        if invariant == "payoff_shortcut":
            return (
                RepairOperator.STRENGTHEN_GUARD
                if iteration % 2 == 0 else RepairOperator.SPLIT_TRANSITION
            )
        if invariant in {"repetitive_grind", "non_evolving_loop"}:
            return RepairOperator.DIMINISHING_RETURN
        if invariant == "reachable_stuck_state":
            return RepairOperator.INTRODUCE_EXIT
        return RepairOperator.STRENGTHEN_GUARD

    def apply_operator(
        self,
        program: DSLProgram,
        counterexample: Counterexample,
        operator: RepairOperator,
    ) -> DSLProgram:
        if operator == RepairOperator.STRENGTHEN_GUARD:
            return self._strengthen_guard(program, counterexample)
        if operator == RepairOperator.SPLIT_TRANSITION:
            return self._split_transition(program, counterexample)
        if operator == RepairOperator.DIMINISHING_RETURN:
            return self._diminishing_return(program, counterexample)
        return self._introduce_exit(program)

    @staticmethod
    def _action(program: DSLProgram, name: str) -> DSLAction | None:
        return next((action for action in program.actions if action.name == name), None)

    def _strengthen_guard(
        self, program: DSLProgram, counterexample: Counterexample
    ) -> DSLProgram:
        target_name = counterexample.witness_actions[-1]
        target = self._action(program, target_name)
        if target is None:
            return program
        simulator = StateMachineSimulator(program)
        state = simulator.initial_state()
        for action_name in counterexample.witness_actions[:-1]:
            try:
                state = simulator.transition(state, action_name)
            except ValueError:
                return program
        guarded = {guard.var_name for guard in target.guards}
        affected = {effect.var_name for effect in target.effects}
        candidate = next(
            (
                name for name, value in state.items()
                if name not in guarded
                and name not in affected
                and value != program.states[name].initial_value
            ),
            None,
        )
        if candidate is None:
            # No existing proposition distinguishes the witness.  Add a
            # bounded usage proposition and make the counterexample's final
            # repetition unavailable.
            uses = counterexample.witness_actions.count(target_name)
            limit = max(0, uses - 1)
            state_name = self._unique_name(program, f"repair_guard_{target_name}")
            states = dict(program.states)
            states[state_name] = StateVariable(
                name=state_name,
                var_type="int",
                initial_value=0,
                min_val=0,
                max_val=max(0, limit),
            )
            replacement = target.model_copy(update={
                "guards": (*target.guards, GuardCondition(
                    var_name=state_name,
                    op="lt",
                    value=limit,
                )),
                "effects": (*target.effects, StateEffect(
                    var_name=state_name,
                    op="add",
                    value=1,
                )),
            })
            return DSLProgram(
                states=states,
                actions=tuple(
                    replacement if action.name == target_name else action
                    for action in program.actions
                ),
                terminal_conditions=program.terminal_conditions,
                max_steps=program.max_steps,
            )
        replacement = target.model_copy(update={
            "guards": (*target.guards, GuardCondition(
                var_name=candidate,
                op="eq",
                value=state[candidate],
            )),
        })
        return program.model_copy(update={
            "actions": tuple(
                replacement if action.name == target_name else action
                for action in program.actions
            ),
        })

    def _split_transition(
        self, program: DSLProgram, counterexample: Counterexample
    ) -> DSLProgram:
        counts = Counter(counterexample.witness_actions)
        target_name, stages = max(counts.items(), key=lambda item: (item[1], item[0]))
        target = self._action(program, target_name)
        if target is None or stages < 2:
            return self._introduce_exit(program)
        state_name = self._unique_name(program, f"repair_stage_{target_name}")
        states = dict(program.states)
        states[state_name] = StateVariable(
            name=state_name,
            var_type="enum",
            initial_value="0",
        )
        replacements = tuple(
            target.model_copy(update={
                "name": f"{target.name}__stage_{index + 1}",
                "guards": (*target.guards, GuardCondition(
                    var_name=state_name,
                    op="eq",
                    value=str(index),
                )),
                "effects": (*target.effects, StateEffect(
                    var_name=state_name,
                    op="set",
                    value=str(index + 1),
                )),
            })
            for index in range(stages)
        )
        actions: list[DSLAction] = []
        for action in program.actions:
            actions.extend(replacements if action.name == target_name else (action,))
        return DSLProgram(
            states=states,
            actions=tuple(actions),
            terminal_conditions=program.terminal_conditions,
            max_steps=program.max_steps,
        )

    def _diminishing_return(
        self, program: DSLProgram, counterexample: Counterexample
    ) -> DSLProgram:
        counts = Counter(counterexample.witness_actions)
        target_name, uses = max(counts.items(), key=lambda item: (item[1], item[0]))
        target = self._action(program, target_name)
        if target is None or uses < 2:
            return self._introduce_exit(program)
        state_name = self._unique_name(program, f"repair_uses_{target_name}")
        limit = uses - 1
        states = dict(program.states)
        states[state_name] = StateVariable(
            name=state_name,
            var_type="int",
            initial_value=0,
            min_val=0,
            max_val=limit,
        )
        replacement = target.model_copy(update={
            "guards": (*target.guards, GuardCondition(
                var_name=state_name,
                op="lt",
                value=limit,
            )),
            "effects": (*target.effects, StateEffect(
                var_name=state_name,
                op="add",
                value=1,
            )),
        })
        return DSLProgram(
            states=states,
            actions=tuple(
                replacement if action.name == target_name else action
                for action in program.actions
            ),
            terminal_conditions=program.terminal_conditions,
            max_steps=program.max_steps,
        )

    @staticmethod
    def _introduce_exit(program: DSLProgram) -> DSLProgram:
        base = "repair_exit"
        state_name = base
        suffix = 2
        while state_name in program.states:
            state_name = f"{base}_{suffix}"
            suffix += 1
        states = dict(program.states)
        states[state_name] = StateVariable(
            name=state_name,
            var_type="bool",
            initial_value=False,
        )
        action_name = state_name
        return DSLProgram(
            states=states,
            actions=(*program.actions, DSLAction(
                name=action_name,
                actor="player",
                guards=(GuardCondition(var_name=state_name, op="eq", value=False),),
                effects=(StateEffect(var_name=state_name, op="set", value=True),),
                description="Explicitly exit an otherwise trapped trajectory.",
            )),
            terminal_conditions=(*program.terminal_conditions, TerminalCondition(
                outcome="loss",
                guards=(GuardCondition(var_name=state_name, op="eq", value=True),),
                description="Safe repair exit",
            )),
            max_steps=program.max_steps,
        )

    @staticmethod
    def _unique_name(program: DSLProgram, base: str) -> str:
        name = base
        suffix = 2
        while name in program.states:
            name = f"{base}_{suffix}"
            suffix += 1
        return name
