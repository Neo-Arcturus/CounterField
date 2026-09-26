from creative_agent import AdversarialPlaytester
from creative_agent.dsl import (
    DSLAction,
    DSLProgram,
    GuardCondition,
    StateEffect,
    StateVariable,
    TerminalCondition,
)
from creative_agent.redteam import ChaosBot


def spam_program(target=4, max_steps=8):
    return DSLProgram(
        states={
            "score": StateVariable(
                name="score", var_type="int", initial_value=0, min_val=0, max_val=target
            )
        },
        actions=[DSLAction(
            name="tap",
            actor="player",
            guards=[GuardCondition(var_name="score", op="lt", value=target)],
            effects=[StateEffect(var_name="score", op="add", value=1)],
        )],
        terminal_conditions=[TerminalCondition(
            outcome="win",
            guards=[GuardCondition(var_name="score", op="gte", value=target)],
        )],
        max_steps=max_steps,
    )


def balanced_program():
    stages = ("start", "charged", "aimed", "released", "complete")
    actions = []
    for before, after in zip(stages, stages[1:]):
        actions.append(DSLAction(
            name=f"advance_{after}",
            actor="player",
            guards=[GuardCondition(var_name="stage", op="eq", value=before)],
            effects=[StateEffect(var_name="stage", op="set", value=after)],
        ))
    return DSLProgram(
        states={
            "stage": StateVariable(name="stage", var_type="enum", initial_value="start")
        },
        actions=actions,
        terminal_conditions=[TerminalCondition(
            outcome="win",
            guards=[GuardCondition(var_name="stage", op="eq", value="complete")],
        )],
        max_steps=8,
    )


def test_exploit_bot_catches_single_action_spam_to_win():
    report = AdversarialPlaytester(chaos_episodes=12).run_playtest(spam_program())

    assert report.exploit_detected is True
    assert report.is_passed is False
    issue = next(issue for issue in report.issues if issue.issue_type == "single_action_spam")
    assert issue.bot_name == "ExploitBot"
    assert issue.witness_actions == ("tap", "tap", "tap", "tap")


def test_fatigue_bot_catches_long_repetitive_grind():
    report = AdversarialPlaytester(chaos_episodes=8).run_playtest(
        spam_program(target=30, max_steps=30)
    )

    assert report.fatigue_score >= 0.75
    assert any(issue.issue_type == "repetitive_grind" for issue in report.issues)
    assert report.bot_results["FatigueBot"]["steps_before_payoff"] == 30


def test_chaos_bot_fuzzing_preserves_clamped_invariant_boundaries():
    program = DSLProgram(
        states={
            "energy": StateVariable(
                name="energy", var_type="int", initial_value=0, min_val=0, max_val=3
            )
        },
        actions=[DSLAction(
            name="surge",
            actor="environment",
            effects=[StateEffect(var_name="energy", op="add", value=100)],
        )],
        terminal_conditions=[TerminalCondition(
            outcome="win",
            guards=[GuardCondition(var_name="energy", op="eq", value=3)],
        )],
        max_steps=3,
    )

    result = ChaosBot(episodes=20, seed=7).run(program)

    assert result.metrics["robustness_score"] == 1.0
    assert result.metrics["invariant_failures"] == 0
    assert not any(issue.issue_type == "broken_invariant" for issue in result.issues)


def test_balanced_mechanism_passes_all_red_team_bots():
    report = AdversarialPlaytester(chaos_episodes=24, seed=11).run_playtest(
        balanced_program()
    )

    assert report.is_passed is True
    assert report.exploit_detected is False
    assert report.fatigue_score < 0.6
    assert report.robustness_score >= 0.95
    assert report.issues == []
