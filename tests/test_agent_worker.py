import unittest
from uuid import uuid4

from agent.runtime.queue import AgentRunQueue
from agent.runtime.recorder import AgentRunRecorder
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.service import HistoricalQueryService
from tools.historical.tool_registry import build_historical_tool_registry
from tools.registry.executor import ToolExecutor
from apps.api.main import (
    agent_queue_health,
    enqueue_agent_query,
    get_agent_run,
    process_one_queued_agent_run,
)
from apps.api.settings import AppSettings, QueueSettings
from tools.database.postgres import PostgresClient


class AgentWorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = AppSettings.from_env()
        cls.db_available = PostgresClient(cls.settings.postgres).health_check().ok

    def setUp(self) -> None:
        if not self.db_available:
            self.skipTest("PostgreSQL is not available")

    def test_async_query_is_processed_by_worker(self) -> None:
        queued = enqueue_agent_query(
            {"input": "755年中国发生安史之乱时，中东发生了什么？", "user_id": "test"}
        )
        pending_run = get_agent_run(queued["run_id"])

        result = process_one_queued_agent_run()
        completed_run = get_agent_run(queued["run_id"])

        self.assertTrue(queued["queued"])
        self.assertEqual(pending_run["status"], "pending")
        self.assertTrue(result["processed"])
        self.assertEqual(result["run_id"], queued["run_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(completed_run["status"], "completed")
        self.assertIn("安史之乱爆发", completed_run["final_answer"])

    def test_redis_queue_requeues_failed_processing_run(self) -> None:
        queue = AgentRunQueue(
            AgentRunRecorder(self.settings.postgres),
            QueueSettings(queue_name=f"test-agent-runs-{uuid4()}"),
        )
        if not queue.redis.ping():
            self.skipTest("Redis is not available")

        queued = queue.enqueue("755年中东发生了什么？", user_id="retry-test")
        claimed = queue.claim_next()
        assert claimed is not None
        queue.recorder.fail_run(queued.run_id, "unit-test failure")

        failure = queue.fail(queued.run_id, "unit-test failure")
        run = queue.recorder.get_run(queued.run_id)
        health = queue.health()

        self.assertEqual(claimed["id"], queued.run_id)
        self.assertEqual(failure["action"], "requeued")
        self.assertEqual(failure["attempts"], 1)
        self.assertEqual(run["status"], "pending")
        self.assertEqual(health["pending_count"], 1)
        self.assertEqual(health["processing_count"], 0)

    def test_redis_queue_dead_letters_after_retry_limit(self) -> None:
        queue = AgentRunQueue(
            AgentRunRecorder(self.settings.postgres),
            QueueSettings(queue_name=f"test-agent-runs-{uuid4()}", max_retries=0),
        )
        if not queue.redis.ping():
            self.skipTest("Redis is not available")

        queued = queue.enqueue("755年中东发生了什么？", user_id="dead-letter-test")
        claimed = queue.claim_next()
        assert claimed is not None
        queue.recorder.fail_run(queued.run_id, "unit-test failure")

        failure = queue.fail(queued.run_id, "unit-test failure")
        run = queue.recorder.get_run(queued.run_id)
        health = queue.health()

        self.assertEqual(failure["action"], "dead_lettered")
        self.assertTrue(failure["dead_lettered"])
        self.assertEqual(run["status"], "failed")
        self.assertEqual(health["pending_count"], 0)
        self.assertEqual(health["processing_count"], 0)
        self.assertEqual(health["dead_count"], 1)

    def test_redis_queue_recovers_stale_processing_run(self) -> None:
        queue = AgentRunQueue(
            AgentRunRecorder(self.settings.postgres),
            QueueSettings(
                queue_name=f"test-agent-runs-{uuid4()}",
                visibility_timeout_seconds=1,
            ),
        )
        if not queue.redis.ping():
            self.skipTest("Redis is not available")

        queued = queue.enqueue("755年中东发生了什么？", user_id="stale-test")
        claimed = queue.claim_next()
        assert claimed is not None
        queue.redis.hset(queue.claimed_at_hash_name, queued.run_id, "1")

        recovery = queue.recover_stale(now=10)
        run = queue.recorder.get_run(queued.run_id)
        health = queue.health()

        self.assertEqual(recovery["recovered"], 1)
        self.assertEqual(recovery["dead_lettered"], 0)
        self.assertEqual(run["status"], "pending")
        self.assertEqual(health["pending_count"], 1)
        self.assertEqual(health["processing_count"], 0)

    def test_redis_queue_dead_letters_stale_run_after_retry_limit(self) -> None:
        queue = AgentRunQueue(
            AgentRunRecorder(self.settings.postgres),
            QueueSettings(
                queue_name=f"test-agent-runs-{uuid4()}",
                max_retries=0,
                visibility_timeout_seconds=1,
            ),
        )
        if not queue.redis.ping():
            self.skipTest("Redis is not available")

        queued = queue.enqueue("755年中东发生了什么？", user_id="stale-dead-test")
        claimed = queue.claim_next()
        assert claimed is not None
        queue.redis.hset(queue.claimed_at_hash_name, queued.run_id, "1")

        recovery = queue.recover_stale(now=10)
        run = queue.recorder.get_run(queued.run_id)
        health = queue.health()

        self.assertEqual(recovery["recovered"], 0)
        self.assertEqual(recovery["dead_lettered"], 1)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(health["pending_count"], 0)
        self.assertEqual(health["processing_count"], 0)
        self.assertEqual(health["dead_count"], 1)

    def test_redis_queue_backend_when_available(self) -> None:
        queue = AgentRunQueue(
            AgentRunRecorder(self.settings.postgres),
            self.settings.queue,
        )
        if not queue.redis.ping():
            self.skipTest("Redis is not available")

        health = agent_queue_health()
        queued = enqueue_agent_query(
            {"input": "755年中国发生安史之乱时，中东发生了什么？", "user_id": "redis-test"}
        )
        result = process_one_queued_agent_run()

        self.assertTrue(health["redis_ok"])
        self.assertEqual(queued["queue_backend"], "redis")
        self.assertTrue(result["processed"])
        self.assertEqual(result["run_id"], queued["run_id"])

    def test_worker_resumes_run_from_recorded_step(self) -> None:
        queue = AgentRunQueue(
            AgentRunRecorder(self.settings.postgres),
            QueueSettings(queue_name=f"test-agent-runs-{uuid4()}"),
        )
        if not queue.redis.ping():
            self.skipTest("Redis is not available")

        user_input = "怛罗斯之战和唐朝、中亚、阿拉伯帝国有什么关系？"
        queued = queue.enqueue(user_input, user_id="worker-resume-test")
        claimed = queue.claim_next()
        assert claimed is not None
        service = HistoricalQueryService(PostgresHistoricalEventRepository(self.settings.postgres))
        resolve_result = ToolExecutor(build_historical_tool_registry(service)).execute(
            "resolve_event",
            {"query": user_input},
        )
        queue.recorder.record_tool_step(
            run_id=queued.run_id,
            step_index=0,
            tool_name="resolve_event",
            tool_arguments=resolve_result.arguments,
            tool_result=resolve_result.observation,
        )
        queue.recorder.mark_running_run_pending_after_timeout(
            queued.run_id,
            "unit-test resume",
        )
        queue.redis.lrem(queue.processing_queue_name, 0, queued.run_id)
        queue.redis.lpush(queue.settings.queue_name, queued.run_id)

        from apps.worker.agent_worker import AgentWorker

        worker = AgentWorker(self.settings)
        worker.queue = queue
        result = worker.process_one()
        run = queue.recorder.get_run(queued.run_id)

        self.assertTrue(result.processed)
        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(run)
        assert run is not None
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["steps"][0]["tool_name"], "resolve_event")
        self.assertEqual(run["steps"][1]["tool_name"], "get_event_detail")


if __name__ == "__main__":
    unittest.main()
