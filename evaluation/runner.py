from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.models.factory import build_model_adapter
from agent.runtime.loop import AgentLoop
from agent.runtime.recorder import AgentRunRecorder
from apps.api.settings import AppSettings
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.service import HistoricalQueryService
from tools.historical.tool_registry import build_historical_tool_registry


DATASET_PATH = ROOT_DIR / "evaluation" / "datasets" / "mvp_questions.json"


@dataclass(frozen=True)
class EvaluationResult:
    case_key: str
    passed: bool
    score: float
    notes: str
    agent_run_id: str | None


class EvaluationRunner:
    def __init__(self) -> None:
        self.settings = AppSettings.from_env().postgres

    def run_dataset(self, dataset_path: Path = DATASET_PATH) -> list[EvaluationResult]:
        cases = json.loads(dataset_path.read_text(encoding="utf-8"))
        results: list[EvaluationResult] = []
        service = HistoricalQueryService(PostgresHistoricalEventRepository(self.settings))
        agent = AgentLoop(
            model_adapter=build_model_adapter(AppSettings.from_env().model),
            tool_registry=build_historical_tool_registry(service),
            recorder=AgentRunRecorder(self.settings),
        )

        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            for case in cases:
                case_id = self._upsert_case(conn, case)
                response = agent.run(case["input"])
                result = self._grade_case(case, response)
                self._insert_result(conn, case_id, result)
                results.append(result)
            conn.commit()

        return results

    def _upsert_case(self, conn: psycopg.Connection, case: dict[str, Any]) -> str:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_cases (
                  case_key,
                  user_input,
                  expected_tools,
                  forbidden_tools,
                  expected_answer_points,
                  max_steps,
                  enabled
                )
                VALUES (%s, %s, %s, %s, %s, %s, true)
                ON CONFLICT (case_key) DO UPDATE SET
                  user_input = EXCLUDED.user_input,
                  expected_tools = EXCLUDED.expected_tools,
                  forbidden_tools = EXCLUDED.forbidden_tools,
                  expected_answer_points = EXCLUDED.expected_answer_points,
                  max_steps = EXCLUDED.max_steps,
                  enabled = true
                RETURNING id::text
                """,
                [
                    case["id"],
                    case["input"],
                    case.get("expected_tools", []),
                    case.get("forbidden_tools", []),
                    case.get("expected_answer_points", []),
                    case.get("max_steps", 8),
                ],
            )
            return cur.fetchone()["id"]

    def _grade_case(self, case: dict[str, Any], response: Any) -> EvaluationResult:
        called_tools = [step.tool_name for step in response.steps]
        expected_tools = case.get("expected_tools", [])
        forbidden_tools = case.get("forbidden_tools", [])
        expected_answer_points = case.get("expected_answer_points", [])
        max_steps = case.get("max_steps", 8)

        checks: list[tuple[str, bool]] = []
        missing_tools = [tool for tool in expected_tools if tool not in called_tools]
        forbidden_called = [tool for tool in forbidden_tools if tool in called_tools]
        answer = response.answer
        missing_points = [
            point for point in expected_answer_points if not self._answer_contains(answer, point)
        ]
        too_many_steps = len(called_tools) > max_steps

        checks.append(("expected_tools", not missing_tools))
        checks.append(("forbidden_tools", not forbidden_called))
        checks.append(("answer_points", not missing_points))
        checks.append(("max_steps", not too_many_steps))

        passed_checks = sum(1 for _, ok in checks if ok)
        score = round(passed_checks / len(checks), 2)
        passed = all(ok for _, ok in checks)
        notes = {
            "called_tools": called_tools,
            "missing_tools": missing_tools,
            "forbidden_called": forbidden_called,
            "missing_answer_points": missing_points,
            "step_count": len(called_tools),
            "max_steps": max_steps,
        }

        return EvaluationResult(
            case_key=case["id"],
            passed=passed,
            score=score,
            notes=json.dumps(notes, ensure_ascii=False),
            agent_run_id=response.run_id,
        )

    def _answer_contains(self, answer: str, point: str) -> bool:
        equivalent_terms = {
            "表格": ["表格", "对照表"],
        }
        if point in equivalent_terms:
            return any(term in answer for term in equivalent_terms[point])
        alternatives = [item.strip() for item in point.split("或")]
        return any(item and item in answer for item in alternatives)

    def _insert_result(
        self,
        conn: psycopg.Connection,
        case_id: str,
        result: EvaluationResult,
    ) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_runs (
                  case_id,
                  agent_run_id,
                  score,
                  passed,
                  notes
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    case_id,
                    result.agent_run_id,
                    result.score,
                    result.passed,
                    result.notes,
                ],
            )


def main() -> int:
    runner = EvaluationRunner()
    results = runner.run_dataset()
    passed = sum(1 for result in results if result.passed)
    print(f"Evaluation complete: {passed}/{len(results)} passed")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"- {result.case_key}: {status} score={result.score} notes={result.notes}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
