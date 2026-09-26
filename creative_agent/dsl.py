"""Declarative simulation DSL and deterministic state-machine runtime.

The interpreter in this module only dispatches explicitly modelled operations.  DSL
input is data: no expression language, dynamic import, ``eval``, or ``exec`` is
supported.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Literal, TypeAlias

from pydantic import Field, field_validator, model_validator

from .models import CanonicalMechanism, CausalLink, StrictModel, clean


Scalar: TypeAlias = int | float | bool | str
State: TypeAlias = dict[str, Scalar]


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class StateVariable(StrictModel):
    name: str
    var_type: Literal["int", "float", "bool", "enum"]
    initial_value: Scalar
    min_val: int | float | None = None
    max_val: int | float | None = None

    _name = field_validator("name")(clean)

    @model_validator(mode="after")
    def validate_definition(self):
        value = self.initial_value
        if self.var_type == "int" and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError("int state variables require an integer initial_value")
        if self.var_type == "float" and not _is_number(value):
            raise ValueError("float state variables require a numeric initial_value")
        if self.var_type == "bool" and not isinstance(value, bool):
            raise ValueError("bool state variables require a boolean initial_value")
        if self.var_type == "enum" and not isinstance(value, str):
            raise ValueError("enum state variables require a string initial_value")
        if self.var_type == "int" and any(
            bound is not None and (not isinstance(bound, int) or isinstance(bound, bool))
            for bound in (self.min_val, self.max_val)
        ):
            raise ValueError("int state variables require integer bounds")
        if _is_number(value) and not math.isfinite(value):
            raise ValueError("numeric initial_value must be finite")
        if self.min_val is not None and not math.isfinite(self.min_val):
            raise ValueError("min_val must be finite")
        if self.max_val is not None and not math.isfinite(self.max_val):
            raise ValueError("max_val must be finite")
        if self.var_type in {"bool", "enum"} and (self.min_val is not None or self.max_val is not None):
            raise ValueError("only numeric state variables may define min_val/max_val")
        if self.min_val is not None and self.max_val is not None and self.min_val > self.max_val:
            raise ValueError("min_val must not exceed max_val")
        if self.min_val is not None and value < self.min_val:
            raise ValueError("initial_value is below min_val")
        if self.max_val is not None and value > self.max_val:
            raise ValueError("initial_value is above max_val")
        return self


class GuardCondition(StrictModel):
    var_name: str
    op: Literal["eq", "neq", "gt", "gte", "lt", "lte", "in"]
    value: Scalar | tuple[Scalar, ...]

    _var_name = field_validator("var_name")(clean)

    @model_validator(mode="after")
    def validate_operand(self):
        if self.op == "in" and not isinstance(self.value, tuple):
            raise ValueError("the 'in' guard requires a list or tuple value")
        if self.op != "in" and isinstance(self.value, tuple):
            raise ValueError(f"the '{self.op}' guard requires a scalar value")
        if self.op == "in" and not self.value:
            raise ValueError("the 'in' guard requires at least one candidate value")
        return self


class StateEffect(StrictModel):
    var_name: str
    op: Literal["set", "add", "sub", "toggle"]
    value: Scalar | None = None

    _var_name = field_validator("var_name")(clean)

    @model_validator(mode="after")
    def validate_operand(self):
        if self.op in {"set", "add", "sub"} and self.value is None:
            raise ValueError(f"the '{self.op}' effect requires a value")
        return self


class DSLAction(StrictModel):
    name: str
    actor: Literal["player", "adversary", "environment"]
    guards: tuple[GuardCondition, ...] = ()
    effects: tuple[StateEffect, ...]
    description: str = ""

    _name = field_validator("name")(clean)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def require_effect(self):
        if not self.effects:
            raise ValueError("an action must define at least one effect")
        return self


class Proposition(StrictModel):
    """A fact that may be satisfied in the semantic intermediate form."""

    id: str
    label: str
    initially_satisfied: bool = False

    _text = field_validator("id", "label")(clean)


class ActionObligation(StrictModel):
    """An operation required to establish one proposition."""

    id: str
    establishes: str
    description: str = ""

    _text = field_validator("id", "establishes")(clean)


class Dependency(StrictModel):
    """A proposition precondition on an action, not an executable action."""

    proposition_id: str
    action_id: str
    relation: Literal["increases", "decreases", "enables", "prevents", "depends_on"]
    required_value: bool

    _text = field_validator("proposition_id", "action_id")(clean)


class PayoffObligation(StrictModel):
    proposition_id: str

    _proposition = field_validator("proposition_id")(clean)


class SemanticIR(StrictModel):
    """Typed boundary between causal interpretation and executable DSL."""

    propositions: tuple[Proposition, ...]
    actions: tuple[ActionObligation, ...]
    dependencies: tuple[Dependency, ...]
    payoff: PayoffObligation

    @model_validator(mode="after")
    def validate_references(self):
        proposition_ids = {item.id for item in self.propositions}
        action_ids = {item.id for item in self.actions}
        if len(proposition_ids) != len(self.propositions):
            raise ValueError("semantic proposition ids must be unique")
        if len(action_ids) != len(self.actions):
            raise ValueError("semantic action ids must be unique")
        if self.payoff.proposition_id not in proposition_ids:
            raise ValueError("payoff must reference a semantic proposition")
        for action in self.actions:
            if action.establishes not in proposition_ids:
                raise ValueError("actions must establish known propositions")
        for dependency in self.dependencies:
            if dependency.proposition_id not in proposition_ids:
                raise ValueError("dependencies must reference known propositions")
            if dependency.action_id not in action_ids:
                raise ValueError("dependencies must reference known actions")
        return self


class CompilationInvariantReport(StrictModel):
    is_valid: bool
    violations: tuple[str, ...] = ()


class CompilationInvariantError(ValueError):
    def __init__(self, report: CompilationInvariantReport):
        self.report = report
        super().__init__("DSL compilation invariants failed: " + "; ".join(report.violations))


class TerminalCondition(StrictModel):
    """A conjunction of guards which produces a terminal outcome."""

    outcome: Literal["win", "loss"]
    guards: tuple[GuardCondition, ...]
    description: str = ""

    @model_validator(mode="after")
    def require_guard(self):
        if not self.guards:
            raise ValueError("a terminal condition must define at least one guard")
        return self


class DSLProgram(StrictModel):
    states: dict[str, StateVariable]
    actions: tuple[DSLAction, ...]
    terminal_conditions: tuple[TerminalCondition, ...]
    max_steps: int = Field(default=50, gt=0, le=10_000)

    @field_validator("terminal_conditions", mode="before")
    @classmethod
    def normalize_terminal_conditions(cls, value):
        """Accept the concise ``{"win": [...], "loss": [...]}`` data form too."""
        if isinstance(value, Mapping):
            unknown = set(value) - {"win", "loss"}
            if unknown:
                raise ValueError(f"unknown terminal outcomes: {sorted(unknown)}")
            normalized = []
            for outcome, guards in value.items():
                if isinstance(guards, GuardCondition) or (
                    isinstance(guards, Mapping) and "var_name" in guards
                ):
                    guards = [guards]
                normalized.append({"outcome": outcome, "guards": guards})
            return normalized
        if isinstance(value, (list, tuple)) and value and all(
            isinstance(item, GuardCondition)
            or (isinstance(item, Mapping) and "var_name" in item and "op" in item)
            for item in value
        ):
            # A bare list is a convenient OR-list of winning conditions.
            return [{"outcome": "win", "guards": [guard]} for guard in value]
        return value

    @model_validator(mode="after")
    def validate_references_and_types(self):
        if not self.states:
            raise ValueError("a program must define at least one state variable")
        for key, variable in self.states.items():
            if key != variable.name:
                raise ValueError(f"state key '{key}' does not match variable name '{variable.name}'")
        names = [action.name for action in self.actions]
        if len(names) != len(set(names)):
            raise ValueError("action names must be unique")
        for action in self.actions:
            for guard in action.guards:
                self._validate_guard(guard)
            for effect in action.effects:
                self._validate_effect(effect)
        for terminal in self.terminal_conditions:
            for guard in terminal.guards:
                self._validate_guard(guard)
        return self

    def _variable(self, name: str) -> StateVariable:
        try:
            return self.states[name]
        except KeyError as exc:
            raise ValueError(f"unknown state variable '{name}'") from exc

    def _validate_guard(self, guard: GuardCondition) -> None:
        variable = self._variable(guard.var_name)
        operands = guard.value if isinstance(guard.value, tuple) else (guard.value,)
        if guard.op in {"gt", "gte", "lt", "lte"} and variable.var_type not in {"int", "float"}:
            raise ValueError(f"ordered comparison requires numeric variable '{guard.var_name}'")
        for operand in operands:
            if not _value_matches(variable, operand):
                raise ValueError(f"guard value does not match type of '{guard.var_name}'")
            if _is_number(operand) and not math.isfinite(operand):
                raise ValueError("numeric guard values must be finite")

    def _validate_effect(self, effect: StateEffect) -> None:
        variable = self._variable(effect.var_name)
        if effect.op in {"add", "sub"}:
            if variable.var_type not in {"int", "float"} or not _is_number(effect.value):
                raise ValueError(f"'{effect.op}' requires a numeric state variable and value")
            if variable.var_type == "int" and not isinstance(effect.value, int):
                raise ValueError(f"integer variable '{effect.var_name}' requires integer arithmetic")
        elif effect.op == "toggle":
            if variable.var_type != "bool":
                raise ValueError("'toggle' requires a boolean state variable")
        elif effect.value is None or not _value_matches(variable, effect.value):
            raise ValueError(f"effect value does not match type of '{effect.var_name}'")
        if _is_number(effect.value) and not math.isfinite(effect.value):
            raise ValueError("numeric effect values must be finite")


def _value_matches(variable: StateVariable, value: object) -> bool:
    if variable.var_type == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if variable.var_type == "float":
        return _is_number(value)
    if variable.var_type == "bool":
        return isinstance(value, bool)
    return isinstance(value, str)


class SimulationStep(StrictModel):
    step: int = Field(ge=1)
    action: str
    actor: Literal["player", "adversary", "environment"]
    state_before: dict[str, Scalar]
    state_after: dict[str, Scalar]


class SimulationTrace(StrictModel):
    steps_taken: int = Field(ge=0)
    terminal_reached: bool
    outcome: Literal["win", "loss", "timeout", "stuck"]
    trajectory: tuple[SimulationStep, ...] = ()
    active_invariants_preserved: bool


class SimulationReport(StrictModel):
    win_rate: float = Field(ge=0, le=1)
    avg_steps_to_payoff: float = Field(ge=0)
    stuck_rate: float = Field(ge=0, le=1)
    branch_factor: float = Field(ge=0)


Policy: TypeAlias = Callable[[Mapping[str, Scalar], tuple[DSLAction, ...]], str | DSLAction]


class DSLInterpreter:
    """Execute a :class:`DSLProgram` with deterministic, enumerated operations."""

    def __init__(self, program: DSLProgram):
        self.program = program
        self.state = self.initial_state()

    def initial_state(self) -> State:
        return {name: variable.initial_value for name, variable in self.program.states.items()}

    def reset(self) -> State:
        self.state = self.initial_state()
        return dict(self.state)

    @staticmethod
    def _guard_holds(guard: GuardCondition, state: Mapping[str, Scalar]) -> bool:
        current = state[guard.var_name]
        if guard.op == "eq":
            return current == guard.value
        if guard.op == "neq":
            return current != guard.value
        if guard.op == "gt":
            return current > guard.value
        if guard.op == "gte":
            return current >= guard.value
        if guard.op == "lt":
            return current < guard.value
        if guard.op == "lte":
            return current <= guard.value
        return current in guard.value

    def guards_hold(self, guards: Sequence[GuardCondition], state: Mapping[str, Scalar] | None = None) -> bool:
        target = self.state if state is None else state
        self._validate_state(target)
        return all(self._guard_holds(guard, target) for guard in guards)

    def available_actions(self, state: Mapping[str, Scalar] | None = None) -> tuple[DSLAction, ...]:
        target = self.state if state is None else state
        return tuple(action for action in self.program.actions if self.guards_hold(action.guards, target))

    def terminal_outcome(self, state: Mapping[str, Scalar] | None = None) -> Literal["win", "loss"] | None:
        target = self.state if state is None else state
        for terminal in self.program.terminal_conditions:
            if self.guards_hold(terminal.guards, target):
                return terminal.outcome
        return None

    def transition(self, state: Mapping[str, Scalar], action: str | DSLAction) -> State:
        """Return the next state without mutating the interpreter."""
        self._validate_state(state)
        selected = self._resolve_action(action)
        if not self.guards_hold(selected.guards, state):
            raise ValueError(f"guards are not satisfied for action '{selected.name}'")
        updated = dict(state)
        for effect in selected.effects:
            variable = self.program.states[effect.var_name]
            current = updated[effect.var_name]
            if effect.op == "set":
                result = effect.value
            elif effect.op == "add":
                result = current + effect.value
            elif effect.op == "sub":
                result = current - effect.value
            else:
                result = not current
            if variable.min_val is not None:
                result = max(variable.min_val, result)
            if variable.max_val is not None:
                result = min(variable.max_val, result)
            if variable.var_type == "float":
                result = float(result)
            updated[effect.var_name] = result
        self._validate_state(updated)
        return updated

    def step(self, action: str | DSLAction, state: Mapping[str, Scalar] | None = None) -> State:
        """Apply an action; explicit state makes this a stateless convenience call."""
        source = self.state if state is None else state
        updated = self.transition(source, action)
        if state is None:
            self.state = updated
        return dict(updated)

    def execute_action(self, state: Mapping[str, Scalar], action: str | DSLAction) -> State:
        """Compatibility-friendly name for a pure state transition."""
        return self.transition(state, action)

    def run(
        self,
        policy: Literal["first", "random", "greedy", "payoff-seeking"] | Policy = "first",
        *,
        seed: int = 0,
        max_steps: int | None = None,
        initial_state: Mapping[str, Scalar] | None = None,
    ) -> SimulationTrace:
        limit = self.program.max_steps if max_steps is None else min(max_steps, self.program.max_steps)
        if limit <= 0:
            raise ValueError("max_steps must be greater than zero")
        state = dict(self.initial_state() if initial_state is None else initial_state)
        self._validate_state(state)
        rng = random.Random(seed)
        trajectory: list[SimulationStep] = []
        invariants_preserved = True

        outcome = self.terminal_outcome(state)
        if outcome:
            self.state = dict(state)
            return SimulationTrace(
                steps_taken=0, terminal_reached=True, outcome=outcome,
                trajectory=(), active_invariants_preserved=True,
            )

        for number in range(1, limit + 1):
            available = self.available_actions(state)
            if not available:
                self.state = dict(state)
                return SimulationTrace(
                    steps_taken=len(trajectory), terminal_reached=False, outcome="stuck",
                    trajectory=tuple(trajectory), active_invariants_preserved=invariants_preserved,
                )
            selected = self._select(policy, state, available, rng)
            before = dict(state)
            state = self.transition(state, selected)
            try:
                self._validate_state(state)
            except ValueError:
                invariants_preserved = False
                raise
            trajectory.append(SimulationStep(
                step=number, action=selected.name, actor=selected.actor,
                state_before=before, state_after=dict(state),
            ))
            outcome = self.terminal_outcome(state)
            if outcome:
                self.state = dict(state)
                return SimulationTrace(
                    steps_taken=number, terminal_reached=True, outcome=outcome,
                    trajectory=tuple(trajectory), active_invariants_preserved=invariants_preserved,
                )

        self.state = dict(state)
        return SimulationTrace(
            steps_taken=len(trajectory), terminal_reached=False, outcome="timeout",
            trajectory=tuple(trajectory), active_invariants_preserved=invariants_preserved,
        )

    def report(
        self,
        runs: int = 100,
        policy: Literal["first", "random", "greedy", "payoff-seeking"] | Policy = "random",
        *,
        seed: int = 0,
    ) -> SimulationReport:
        if runs <= 0:
            raise ValueError("runs must be greater than zero")
        traces: list[SimulationTrace] = []
        branch_counts: list[int] = []
        for run_number in range(runs):
            trace = self.run(policy, seed=seed + run_number)
            traces.append(trace)
            if not trace.trajectory:
                branch_counts.append(len(self.available_actions(self.initial_state())))
            else:
                branch_counts.extend(
                    len(self.available_actions(step.state_before)) for step in trace.trajectory
                )
        wins = [trace for trace in traces if trace.outcome == "win"]
        return SimulationReport(
            win_rate=len(wins) / runs,
            avg_steps_to_payoff=(sum(trace.steps_taken for trace in wins) / len(wins)) if wins else 0.0,
            stuck_rate=sum(trace.outcome == "stuck" for trace in traces) / runs,
            branch_factor=(sum(branch_counts) / len(branch_counts)) if branch_counts else 0.0,
        )

    def _resolve_action(self, action: str | DSLAction) -> DSLAction:
        name = action.name if isinstance(action, DSLAction) else action
        for candidate in self.program.actions:
            if candidate.name == name:
                return candidate
        raise ValueError(f"unknown action '{name}'")

    def _select(self, policy, state, available, rng: random.Random) -> DSLAction:
        if callable(policy):
            return self._resolve_available(policy(dict(state), available), available)
        if policy == "first":
            return available[0]
        if policy == "random":
            return rng.choice(available)
        if policy in {"greedy", "payoff-seeking"}:
            scored = []
            for index, action in enumerate(available):
                successor = self.transition(state, action)
                terminal = self.terminal_outcome(successor)
                score = 2 if terminal == "win" else -2 if terminal == "loss" else self._terminal_progress(successor)
                scored.append((score, -index, action))
            return max(scored, key=lambda item: (item[0], item[1]))[2]
        raise ValueError(f"unknown policy '{policy}'")

    def _resolve_available(self, choice: str | DSLAction, available: tuple[DSLAction, ...]) -> DSLAction:
        name = choice.name if isinstance(choice, DSLAction) else choice
        for action in available:
            if action.name == name:
                return action
        raise ValueError(f"policy selected unavailable action '{name}'")

    def _terminal_progress(self, state: Mapping[str, Scalar]) -> float:
        win_conditions = [t for t in self.program.terminal_conditions if t.outcome == "win"]
        if not win_conditions:
            return 0.0
        return max(
            sum(self._guard_progress(guard, state) for guard in terminal.guards) / len(terminal.guards)
            for terminal in win_conditions
        )

    def _guard_progress(self, guard: GuardCondition, state: Mapping[str, Scalar]) -> float:
        if self._guard_holds(guard, state):
            return 1.0
        current = state[guard.var_name]
        target = guard.value
        if _is_number(current) and _is_number(target):
            if guard.op in {"eq", "gt", "gte", "lt", "lte"}:
                return 1.0 / (1.0 + abs(target - current))
        return 0.0

    def _validate_state(self, state: Mapping[str, Scalar]) -> None:
        if set(state) != set(self.program.states):
            raise ValueError("state keys must exactly match the program state variables")
        for name, variable in self.program.states.items():
            value = state[name]
            if not _value_matches(variable, value):
                raise ValueError(f"state value does not match type of '{name}'")
            if _is_number(value) and not math.isfinite(value):
                raise ValueError(f"state value for '{name}' must be finite")
            if variable.min_val is not None and value < variable.min_val:
                raise ValueError(f"state value for '{name}' is below min_val")
            if variable.max_val is not None and value > variable.max_val:
                raise ValueError(f"state value for '{name}' is above max_val")


class StateMachineSimulator(DSLInterpreter):
    """Domain-oriented name for :class:`DSLInterpreter`."""


def _identifier(text: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_") or "state"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def mechanism_to_semantic_ir(mechanism: CanonicalMechanism) -> SemanticIR:
    """Interpret a causal graph as obligations without making edges executable.

    Multiple links targeting the same proposition become dependencies of one
    synthesized action.  Inhibitory links require their source proposition to
    be absent; all other links require it to be present.
    """
    def node_key(value: str) -> str:
        return " ".join(value.casefold().split())

    labels_by_key: dict[str, str] = {}
    for link in mechanism.causal_structure:
        for label in (link.cause, link.effect):
            labels_by_key.setdefault(node_key(label), label)
    payoff_key = node_key(mechanism.payoff)
    labels_by_key.setdefault(payoff_key, mechanism.payoff)
    used: set[str] = set()
    names = {
        key: _identifier(label, used) for key, label in labels_by_key.items()
    }
    incoming = {node_key(link.effect) for link in mechanism.causal_structure}
    propositions = tuple(
        Proposition(
            id=names[key],
            label=label,
            initially_satisfied=key not in incoming and key != payoff_key,
        )
        for key, label in labels_by_key.items()
    )

    action_used: set[str] = set()
    action_by_effect: dict[str, str] = {}
    actions: list[ActionObligation] = []
    for effect_key, effect_label in labels_by_key.items():
        links = [
            link for link in mechanism.causal_structure
            if node_key(link.effect) == effect_key
        ]
        if not links:
            continue
        action_id = _identifier(f"satisfy_{effect_label}", action_used)
        action_by_effect[effect_key] = action_id
        actions.append(ActionObligation(
            id=action_id,
            establishes=names[effect_key],
            description="; ".join(
                f"{link.cause} {link.relation} {link.effect}" for link in links
            ),
        ))

    dependencies = tuple(
        Dependency(
            proposition_id=names[node_key(link.cause)],
            action_id=action_by_effect[node_key(link.effect)],
            relation=link.relation,
            required_value=link.relation not in {"prevents", "decreases"},
        )
        for link in mechanism.causal_structure
    )
    return SemanticIR(
        propositions=propositions,
        actions=tuple(actions),
        dependencies=dependencies,
        payoff=PayoffObligation(proposition_id=names[payoff_key]),
    )


def compile_semantic_ir(ir: SemanticIR, *, max_steps: int = 50) -> DSLProgram:
    """Compile semantic obligations into guarded state-machine transitions."""
    states = {
        proposition.id: StateVariable(
            name=proposition.id,
            var_type="bool",
            initial_value=proposition.initially_satisfied,
        )
        for proposition in ir.propositions
    }
    actions = []
    for obligation in ir.actions:
        dependencies = tuple(
            dependency for dependency in ir.dependencies
            if dependency.action_id == obligation.id
        )
        guards = [
            GuardCondition(
                var_name=dependency.proposition_id,
                op="eq",
                value=dependency.required_value,
            )
            for dependency in dependencies
        ]
        guards.append(GuardCondition(
            var_name=obligation.establishes,
            op="neq",
            value=True,
        ))
        actions.append(DSLAction(
            name=obligation.id,
            actor="environment",
            guards=tuple(guards),
            effects=(StateEffect(
                var_name=obligation.establishes,
                op="set",
                value=True,
            ),),
            description=obligation.description,
        ))

    program = DSLProgram(
        states=states,
        actions=tuple(actions),
        terminal_conditions=(TerminalCondition(
            outcome="win",
            guards=(GuardCondition(
                var_name=ir.payoff.proposition_id,
                op="eq",
                value=True,
            ),),
            description="semantic payoff",
        ),),
        max_steps=max_steps,
    )
    report = verify_compilation_invariants(ir, program)
    if not report.is_valid:
        raise CompilationInvariantError(report)
    return program


def verify_compilation_invariants(
    ir: SemanticIR, program: DSLProgram
) -> CompilationInvariantReport:
    """Verify that compilation preserved obligations and dependency guards."""
    violations: list[str] = []
    proposition_ids = {item.id for item in ir.propositions}
    if set(program.states) != proposition_ids:
        violations.append("program states do not exactly represent propositions")
    for proposition in ir.propositions:
        state = program.states.get(proposition.id)
        if state is None:
            continue
        if (
            state.var_type != "bool"
            or state.initial_value != proposition.initially_satisfied
        ):
            violations.append(
                f"state '{proposition.id}' does not preserve its proposition initialization"
            )

    actions_by_name = {action.name: action for action in program.actions}
    if set(actions_by_name) != {action.id for action in ir.actions}:
        violations.append("program actions do not exactly represent action obligations")

    for obligation in ir.actions:
        action = actions_by_name.get(obligation.id)
        if action is None:
            continue
        expected_effect = StateEffect(
            var_name=obligation.establishes,
            op="set",
            value=True,
        )
        if action.effects != (expected_effect,):
            violations.append(f"action '{obligation.id}' does not establish its proposition")
        actual_guards = {(guard.var_name, guard.op, guard.value) for guard in action.guards}
        for dependency in (
            item for item in ir.dependencies if item.action_id == obligation.id
        ):
            required = (dependency.proposition_id, "eq", dependency.required_value)
            if required not in actual_guards:
                violations.append(
                    f"dependency '{dependency.relation}' is not a guard on '{obligation.id}'"
                )

    payoff_guard = GuardCondition(
        var_name=ir.payoff.proposition_id,
        op="eq",
        value=True,
    )
    win_guards = {
        guard
        for terminal in program.terminal_conditions
        if terminal.outcome == "win"
        for guard in terminal.guards
    }
    if payoff_guard not in win_guards:
        violations.append("payoff obligation is not represented by a win condition")
    payoff_state = program.states.get(ir.payoff.proposition_id)
    if payoff_state is not None and payoff_state.initial_value is not False:
        violations.append("payoff proposition must not be initially satisfied")

    payoff_actions = [
        item for item in ir.actions if item.establishes == ir.payoff.proposition_id
    ]
    for payoff_action in payoff_actions:
        compiled = actions_by_name.get(payoff_action.id)
        if compiled is None:
            continue
        expected_dependencies = {
            (item.proposition_id, item.required_value)
            for item in ir.dependencies if item.action_id == payoff_action.id
        }
        actual_dependencies = {
            (guard.var_name, guard.value)
            for guard in compiled.guards if guard.op == "eq"
        }
        if not expected_dependencies <= actual_dependencies:
            violations.append("a payoff action can bypass prerequisite propositions")

    return CompilationInvariantReport(
        is_valid=not violations,
        violations=tuple(violations),
    )


def canonical_mechanism_to_dsl(mechanism: CanonicalMechanism, *, max_steps: int = 50) -> DSLProgram:
    """Compile a causal graph through a typed semantic IR into executable DSL."""
    return compile_semantic_ir(mechanism_to_semantic_ir(mechanism), max_steps=max_steps)


def dsl_program_to_mechanism(
    program: DSLProgram,
    *,
    core_mechanism: str = "Declarative state-machine simulation",
    affected_system: str = "simulated system",
) -> CanonicalMechanism:
    """Summarize DSL action dependencies as a canonical causal mechanism."""
    links: list[CausalLink] = []
    for action in program.actions:
        causes = [guard.var_name for guard in action.guards] or [action.name]
        for cause in causes:
            for effect in action.effects:
                relation = "increases" if effect.op == "add" else "decreases" if effect.op == "sub" else "enables"
                links.append(CausalLink(cause=cause, relation=relation, effect=effect.var_name))
    win = next((terminal for terminal in program.terminal_conditions if terminal.outcome == "win"), None)
    payoff = win.guards[0].var_name if win else "terminal outcome"
    return CanonicalMechanism(
        core_mechanism=core_mechanism,
        causal_structure=tuple(links),
        affected_system=affected_system,
        payoff=payoff,
    )


def simulate_program(
    program: DSLProgram,
    policy: Literal["first", "random", "greedy", "payoff-seeking"] | Policy = "first",
    *,
    seed: int = 0,
) -> SimulationTrace:
    return StateMachineSimulator(program).run(policy, seed=seed)
