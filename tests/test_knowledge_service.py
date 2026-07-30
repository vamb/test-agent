import unittest

from apps.api.main import (
    get_knowledge_document_chunks,
    get_vector_status,
    create_vector_rebuild_job,
    get_vector_rebuild_job,
    ingest_knowledge_document,
    list_knowledge_documents,
    process_vector_rebuild_job,
    rebuild_vectors,
    reembed_knowledge_document,
    search_knowledge,
    update_knowledge_document,
)
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
        self.assertTrue(any("安史之乱" in item["content"] for item in result["results"]))
        self.assertTrue(any(item["citation"] == "测试资料：安史之乱" for item in result["results"]))

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

    def test_document_management_and_vector_status(self) -> None:
        document = ingest_knowledge_document(
            {
                "title": "知识库管理测试资料",
                "content": "这是一段用于测试知识库文档列表、chunk 查看和向量重算的资料。",
                "citation": "测试资料：知识库管理",
                "created_by": "test",
            }
        )
        documents = list_knowledge_documents(query="知识库管理测试", limit=5)
        chunks = get_knowledge_document_chunks(document["document_id"])
        updated = update_knowledge_document(
            document["document_id"],
            {"updates": {"status": "inactive"}},
        )
        reembedded = reembed_knowledge_document(document["document_id"])
        status = get_vector_status()
        rebuilt = rebuild_vectors({"target": "knowledge", "limit": 5})

        self.assertGreaterEqual(documents["total"], 1)
        self.assertTrue(chunks["found"])
        self.assertGreaterEqual(chunks["total"], 1)
        self.assertTrue(updated["success"])
        self.assertEqual(updated["document"]["status"], "inactive")
        self.assertTrue(reembedded["success"])
        self.assertIn("knowledge_chunks", status)
        self.assertTrue(rebuilt["success"])

    def test_vector_rebuild_job_lifecycle(self) -> None:
        ingest_knowledge_document(
            {
                "title": "向量任务测试资料",
                "content": "这是一段用于测试向量重建任务的资料。",
                "citation": "测试资料：向量任务",
                "created_by": "test",
            }
        )

        created = create_vector_rebuild_job(
            {"target": "knowledge", "limit": 5, "created_by": "test"}
        )
        job_id = created["job"]["id"]
        fetched = get_vector_rebuild_job(job_id)
        processed = process_vector_rebuild_job(job_id)

        self.assertTrue(created["created"])
        self.assertTrue(fetched["found"])
        self.assertTrue(processed["processed"])
        self.assertEqual(processed["job"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
