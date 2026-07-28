import json
import tempfile
import unittest
from pathlib import Path

from evaluation.runner import EvaluationRunner


class EvaluationRunnerTest(unittest.TestCase):
    def test_runner_writes_evaluation_result(self) -> None:
        case = {
            "id": "test_eval_755",
            "input": "755年中国发生安史之乱时，中东和中亚发生了什么？",
            "expected_tools": ["search_events_by_year"],
            "forbidden_tools": ["import_events", "update_event"],
            "expected_answer_points": ["安史之乱", "阿拔斯王朝", "怛罗斯之战"],
            "max_steps": 4,
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            dataset_path = Path(tmp_dir) / "dataset.json"
            dataset_path.write_text(json.dumps([case], ensure_ascii=False), encoding="utf-8")
            results = EvaluationRunner().run_dataset(dataset_path)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].passed)
        self.assertEqual(results[0].score, 1.0)


if __name__ == "__main__":
    unittest.main()

