import argparse
import json
import sys
from .models import HarnessConfig
from .providers import MockIdeaProvider
from .harness import IdeationHarness


SAMPLES = {
    "game-mechanics": "Create a game mechanic that makes cooperation rewarding.",
    "system-design": "Reduce onboarding friction without more meetings.",
}


def main(argv=None):
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--problem")
    source.add_argument("--sample", choices=SAMPLES)
    parser.add_argument("--provider", default="mock", choices=("mock",))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--population-size", type=int, default=6)
    parser.add_argument("--total-budget", type=int, default=18)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--best-of-k", type=int, default=5)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        config = HarnessConfig(workers=args.workers, generations=args.generations, population_size=args.population_size, total_budget=args.total_budget, seed=args.seed)
        result = IdeationHarness(MockIdeaProvider()).run(args.problem or SAMPLES[args.sample], config)
        data = result.model_dump(mode="json")
        if args.format == "json":
            output = json.dumps(data, indent=2)
        else:
            output = f"status: {result.status}\ntermination: {result.termination_reason}\nmetrics: {result.metrics}\nmode: mock scoring; hash-lexical-proxy embeddings\n"
            output += "\n".join(f"- {x.candidate.title}" for x in result.selected)
        if args.output:
            with open(args.output + ".tmp", "w", encoding="utf8") as handle:
                handle.write(output)
            import os
            os.replace(args.output + ".tmp", args.output)
        else:
            print(output)
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
