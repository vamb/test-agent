import unittest

from apps.api.main import ingest_knowledge_document, search_knowledge
from apps.api.settings import AppSettings
from knowledge.service import KnowledgeService
from tools.database.postgres import PostgresClient


class KnowledgeServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = AppSettings.from_env().postgres
        cls.db_available = PostgresClient(cls.settings).health_check().ok

    def setUp(self) -> None:
        if not self.db_available:
            self.skipTest("PostgreSQL is not available")

    def test_ingest_and_search_document(self) -> None:
        service = KnowledgeService(self.settings)
        document = service.ingest_document(
            title="安史之乱测试资料",
            content=(
                "安史之乱爆发于755年，是唐朝由盛转衰的重要事件。"
                "这一事件与唐朝边镇节度使权力扩张、财政压力和军事结构变化有关。"
            ),
            source_type="note",
            citation="测试资料：安史之乱",
            created_by="test",
        )

        result = service.search("安史之乱 唐朝 755", limit=3)

        self.assertEqual(document["chunk_count"], 1)
        self.assertGreaterEqual(result["count"], 1)
        self.assertIn("安史之乱", result["results"][0]["content"])
        self.assertEqual(result["results"][0]["citation"], "测试资料：安史之乱")

    def test_knowledge_api_helpers(self) -> None:
        document = ingest_knowledge_document(
            {
                "title": "怛罗斯之战测试资料",
                "content": "怛罗斯之战发生于751年，涉及唐朝、阿拔斯王朝和中亚势力。",
                "citation": "测试资料：怛罗斯之战",
                "created_by": "test",
            }
        )
        result = search_knowledge("怛罗斯之战 阿拔斯", limit=3)

        self.assertIn("document_id", document)
        self.assertGreaterEqual(result["count"], 1)
        self.assertIn("怛罗斯", result["results"][0]["content"])


if __name__ == "__main__":
    unittest.main()
