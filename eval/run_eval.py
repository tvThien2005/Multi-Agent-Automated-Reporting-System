"""Run the one-shot Text-to-SQL baseline and persist reproducible results."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

# Allow both `python eval/run_eval.py` and `python -m eval.run_eval`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

from src.agents.baseline_sql import (  # noqa: E402
    BaselineResponseError,
    OpenAICompatibleClient,
    parse_baseline_answer,
    read_schema_context,
)
from src.eval.compare import results_match  # noqa: E402
from src.safety.executor import ReadOnlyExecutor  # noqa: E402


def load_questions(path: Path, split: str) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            question = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at {path}:{line_number}") from exc
        question_split = question.get("split", "dev")
        if question_split == split:
            questions.append(question)
    return questions


def table_names_from_schema(schema_context: str) -> set[str]:
    import re

    return set(re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)", schema_context, re.I))


def evaluate_question(
    question: dict[str, Any],
    *,
    client: OpenAICompatibleClient,
    schema_context: str,
    executor: ReadOnlyExecutor,
) -> dict[str, Any]:
    started = perf_counter()
    record: dict[str, Any] = {
        "id": question["id"],
        "difficulty": question["difficulty"],
        "answerable_expected": question["answerable"],
        "correct": False,
    }
    try:
        raw_response = client.complete_once(schema_context=schema_context, question_vi=question["question_vi"])
        answer = parse_baseline_answer(raw_response)
        record.update({"answerable_predicted": answer.answerable, "sql": answer.sql, "reason": answer.reason})
        if not question["answerable"]:
            record["correct"] = not answer.answerable
            record["outcome"] = "correct_refusal" if record["correct"] else "incorrect_refusal"
        elif not answer.answerable:
            record["outcome"] = "unexpected_refusal"
        else:
            gold_result = executor.execute(question["gold_sql"])
            agent_result = executor.execute(answer.sql or "")
            if gold_result.truncated or agent_result.truncated:
                record["outcome"] = "truncated_result"
            else:
                record["correct"] = results_match(
                    gold_result.rows,
                    agent_result.rows,
                    order_matters=question.get("order_matters", False),
                    ignore_column_order=question.get("ignore_column_order", False),
                )
                record["outcome"] = "match" if record["correct"] else "wrong_result"
    except BaselineResponseError as exc:
        record.update({"outcome": "invalid_model_response", "error": str(exc)})
    except Exception as exc:  # Preserve an error per question; evaluation continues.
        record.update({"outcome": "execution_error", "error": f"{type(exc).__name__}: {exc}"})
    record["latency_seconds"] = round(perf_counter() - started, 3)
    return record


def preflight_gold_sql(questions: list[dict[str, Any]], executor: ReadOnlyExecutor) -> list[str]:
    """Run every answerable gold query before spending any LLM calls."""
    errors: list[str] = []
    for question in questions:
        if not question["answerable"]:
            continue
        try:
            executor.execute(question["gold_sql"])
        except Exception as exc:
            errors.append(f"{question['id']}: {type(exc).__name__}: {exc}")
    return errors


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped["overall"] = records
    for record in records:
        grouped[record["difficulty"]].append(record)
    return {
        name: {
            "total": len(group),
            "correct": sum(record["correct"] for record in group),
            "accuracy": round(sum(record["correct"] for record in group) / len(group), 4) if group else None,
        }
        for name, group in grouped.items()
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=Path("eval/questions-v30.jsonl"))
    parser.add_argument("--schema", type=Path, default=Path("db/init/01_schema.sql"))
    parser.add_argument("--split", default="dev", help="Only questions in this split are evaluated (default: dev).")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate all gold SQL against the database, without calling the LLM.",
    )
    parser.add_argument("--output", type=Path, help="Result JSON path; default is eval/results/baseline_<UTC>.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv()
    schema_context = read_schema_context(args.schema)
    questions = load_questions(args.questions, args.split)
    if not questions:
        print(f"No questions in split '{args.split}'.", file=sys.stderr)
        return 2
    executor = ReadOnlyExecutor.from_environment(allowed_tables=table_names_from_schema(schema_context))
    gold_errors = preflight_gold_sql(questions, executor)
    if gold_errors:
        print("Gold SQL preflight failed; no LLM calls were made:", file=sys.stderr)
        print("\n".join(gold_errors), file=sys.stderr)
        return 2
    if args.preflight_only:
        print(f"Gold SQL preflight passed for {len(questions)} questions; no LLM calls were made.")
        return 0
    client = OpenAICompatibleClient.from_environment()
    records = [
        evaluate_question(question, client=client, schema_context=schema_context, executor=executor)
        for question in questions
    ]
    result = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "questions_file": str(args.questions),
        "split": args.split,
        "model": client.model,
        "one_llm_call_per_question": True,
        "summary": summarize(records),
        "records": records,
    }
    output = args.output or Path("eval/results") / f"baseline_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for group, values in result["summary"].items():
        print(f"{group:12} {values['correct']}/{values['total']}  accuracy={values['accuracy']}")
    print(f"Saved results to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
