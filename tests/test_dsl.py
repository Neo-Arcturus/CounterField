import pytest
from pydantic import ValidationError

from creative_agent.dsl import (
    DSLAction,
    DSLInterpreter,
    DSLProgram,
    GuardCondition,
    StateEffect,
    StateMachineSimulator,
    StateVariable,
    TerminalCondition,
    canonical_mechanism_to_dsl,
)
from creative_agent.models import CanonicalMechanism, CausalLink


def counter_program(*, max_steps=5, target=3):
    return DSLProgram(
        states={
            "score": StateVariable(
                name="score", var_type="int", initial_value=0, min_val=0, max_val=target
            )
        },
        actions=[
            DSLAction(
                name="score_point",
                actor="player",
                guards=[GuardCondition(var_name="score", op="lt", value=target)],
                effects=[StateEffect(var_name="score", op="add", value=1)],
                description="Advance toward the payoff.",
            )
        ],
        terminal_conditions=[
            TerminalCondition(
                outcome="win",
                guards=[GuardCondition(var_name="score", op="gte", value=target)],
            )
        ],
        max_steps=max_steps,
    )


def test_dsl_parsing_and_deterministic_clamped_transition():
    program = counter_program(target=2)
    interpreter = DSLInterpreter(program)

    first = interpreter.step("score_point")
    second = interpreter.step("score_point")

    assert first == {"score": 1}
    assert second == {"score": 2}
    # A direct transition uses the same deterministic operation and bound clamp.
    assert interpreter.transition({"score": 1}, "score_point") == {"score": 2}


def test_successful_trace_reaches_win():
    trace = StateMachineSimulator(counter_program()).run(policy="greedy")

    assert trace.terminal_reached is True
    assert trace.outcome == "win"
    assert trace.steps_taken == 3
    assert trace.trajectory[-1].state_after == {"score": 3}
    assert trace.active_invariants_preserved is True


def test_stuck_state_is_detected_before_payoff():
    program = DSLProgram(
        states={"key": StateVariable(name="key", var_type="bool", initial_value=False)},
        actions=[
            DSLAction(
                name="open",
                actor="player",
                guards=[GuardCondition(var_name="key", op="eq", value=True)],
                effects=[StateEffect(var_name="key", op="toggle")],
            )
        ],
        terminal_conditions={
            "win": [GuardCondition(var_name="key", op="eq", value=True)]
        },
        max_steps=4,
    )

    trace = StateMachineSimulator(program).run()

    assert trace.outcome == "stuck"
    assert trace.terminal_reached is False
    assert trace.steps_taken == 0


def test_bounded_runner_times_out():
    program = DSLProgram(
        states={"clock": StateVariable(name="clock", var_type="int", initial_value=0)},
        actions=[
            DSLAction(
                name="tick",
                actor="environment",
                effects=[StateEffect(var_name="clock", op="add", value=1)],
            )
        ],
        terminal_conditions={
            "win": [GuardCondition(var_name="clock", op="gte", value=99)]
        },
        max_steps=3,
    )

    trace = StateMachineSimulator(program).run()

    assert trace.outcome == "timeout"
    assert trace.steps_taken == 3
    assert trace.trajectory[-1].state_after["clock"] == 3


def test_schema_rejects_raw_code_and_code_fields():
    with pytest.raises(ValidationError):
        DSLProgram.model_validate("score += 1")

    payload = counter_program().model_dump()
    payload["code"] = "__import__('os').system('echo unsafe')"
    with pytest.raises(ValidationError):
        DSLProgram.model_validate(payload)


def test_schema_rejects_unknown_variables_and_invalid_effect_types():
    with pytest.raises(ValidationError, match="unknown state variable"):
        DSLProgram(
            states={"ready": StateVariable(name="ready", var_type="bool", initial_value=False)},
            actions=[DSLAction(
                name="bad", actor="player",
                effects=[StateEffect(var_name="missing", op="set", value=True)],
            )],
            terminal_conditions=[],
        )

    with pytest.raises(ValidationError, match="toggle"):
        DSLProgram(
            states={"score": StateVariable(name="score", var_type="int", initial_value=0)},
            actions=[DSLAction(
                name="bad", actor="player",
                effects=[StateEffect(var_name="score", op="toggle")],
            )],
            terminal_conditions=[],
        )


def test_report_contains_aggregate_simulation_metrics():
    report = StateMachineSimulator(counter_program()).report(runs=4, policy="first")

    assert report.win_rate == 1.0
    assert report.avg_steps_to_payoff == 3.0
    assert report.stuck_rate == 0.0
    assert report.branch_factor == 1.0


def test_canonical_mechanism_bridge_produces_executable_dsl():
    mechanism = CanonicalMechanism(
        core_mechanism="A staged feedback path",
        causal_structure=(
            CausalLink(cause="player input", relation="enables", effect="system response"),
            CausalLink(cause="system response", relation="enables", effect="payoff"),
        ),
        affected_system="test loop",
        payoff="payoff",
    )

    program = canonical_mechanism_to_dsl(mechanism, max_steps=4)
    trace = StateMachineSimulator(program).run(policy="first")

    assert trace.outcome == "win"
    assert trace.steps_taken == 2
