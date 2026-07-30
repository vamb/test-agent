import unittest

from apps.api.main import app


class AdminApiSchemaTest(unittest.TestCase):
    def test_admin_write_routes_use_pydantic_request_models(self) -> None:
        schema = app.openapi()
        components = schema["components"]["schemas"]
        self.assertIn("AdminCreateEventRequest", components)
        self.assertIn("AdminUpdateEventRequest", components)
        self.assertIn("AdminSourceRequest", components)
        self.assertIn("AdminRelationRequest", components)
        self.assertIn("AdminQualityIssueActionRequest", components)

        expected_refs = {
            ("post", "/admin/events"): "AdminCreateEventRequest",
            ("patch", "/admin/events/{event_id}"): "AdminUpdateEventRequest",
            ("post", "/admin/events/bulk-update"): "AdminBulkUpdateEventsRequest",
            ("post", "/admin/events/{event_id}/sources"): "AdminSourceRequest",
            ("patch", "/admin/sources/{source_id}"): "AdminUpdateSourceRequest",
            ("post", "/admin/data-quality/issues/actions"): "AdminQualityIssueActionRequest",
            ("post", "/admin/relations"): "AdminRelationRequest",
            ("patch", "/admin/relations/{relation_id}"): "AdminUpdateRelationRequest",
        }
        for (method, path), model_name in expected_refs.items():
            request_schema = schema["paths"][path][method]["requestBody"]["content"]["application/json"]["schema"]
            self.assertEqual(request_schema["$ref"], f"#/components/schemas/{model_name}")
            response_schema = schema["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]
            self.assertEqual(response_schema["$ref"], "#/components/schemas/AdminMutationResponse")

    def test_import_knowledge_and_vector_write_routes_use_request_models(self) -> None:
        schema = app.openapi()
        components = schema["components"]["schemas"]
        self.assertIn("ImportBatchCreateRequest", components)
        self.assertIn("KnowledgeDocumentIngestRequest", components)
        self.assertIn("KnowledgeDocumentRechunkRequest", components)
        self.assertIn("VectorRebuildRequest", components)
        self.assertIn("VectorProcessPendingRequest", components)

        expected_refs = {
            ("post", "/imports/batches"): "ImportBatchCreateRequest",
            ("post", "/imports/parse"): "ImportParseRequest",
            ("patch", "/imports/staging/{row_id}"): "ImportStagingUpdateRequest",
            ("post", "/imports/staging/{row_id}/merge"): "ImportStagingMergeRequest",
            ("post", "/imports/staging/bulk-revalidate"): "ImportBulkRevalidateRequest",
            ("post", "/knowledge/documents"): "KnowledgeDocumentIngestRequest",
            ("patch", "/knowledge/documents/{document_id}"): "KnowledgeDocumentUpdateRequest",
            ("post", "/knowledge/documents/{document_id}/rechunk"): "KnowledgeDocumentRechunkRequest",
            ("post", "/vectors/rebuild-jobs/process-pending"): "VectorProcessPendingRequest",
        }
        for (method, path), model_name in expected_refs.items():
            request_schema = schema["paths"][path][method]["requestBody"]["content"]["application/json"]["schema"]
            self.assertEqual(request_schema["$ref"], f"#/components/schemas/{model_name}")

        vector_schema = schema["paths"]["/vectors/rebuild-jobs"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        self.assertIn("#/components/schemas/VectorRebuildRequest", str(vector_schema))
        import_response = schema["paths"]["/imports/batches"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
        knowledge_response = schema["paths"]["/knowledge/documents"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertEqual(import_response["$ref"], "#/components/schemas/ImportMutationResponse")
        self.assertEqual(knowledge_response["$ref"], "#/components/schemas/KnowledgeMutationResponse")


if __name__ == "__main__":
    unittest.main()
