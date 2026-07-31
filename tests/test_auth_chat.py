import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.dependencies import auth_service, chat_service, memory_service
from apps.api.main import app


class AuthChatTest(unittest.TestCase):
    def test_register_login_logout_session_lifecycle(self) -> None:
        suffix = uuid4().hex[:10]
        username = f"user_{suffix}"
        user = auth_service.register(
            username=username,
            password="secret123",
            email=f"{username}@example.test",
            display_name="Test User",
        )

        self.assertEqual(user["username"], username)
        self.assertNotIn("password_hash", user)

        session = auth_service.login(username, "secret123")
        current_user = auth_service.get_user_by_session(session.token)

        self.assertIsNotNone(current_user)
        self.assertEqual(current_user["id"], user["id"])

        self.assertTrue(auth_service.logout(session.token))
        self.assertIsNone(auth_service.get_user_by_session(session.token))

    def test_chat_group_conversation_messages_and_artifacts_are_user_scoped(self) -> None:
        suffix = uuid4().hex[:10]
        owner = auth_service.register(
            username=f"owner_{suffix}",
            password="secret123",
        )
        other = auth_service.register(
            username=f"other_{suffix}",
            password="secret123",
        )

        group = chat_service.create_group(owner["id"], "唐朝专题", "安史之乱相关")
        conversation = chat_service.create_conversation(
            owner["id"],
            title="755 年同期事件",
            group_id=group["id"],
        )
        user_message = chat_service.store_user_message(
            owner["id"],
            "755年中国发生安史之乱时，中东发生了什么？",
            conversation_id=conversation["id"],
        )
        assistant_message = chat_service.create_message(
            user_id=owner["id"],
            conversation_id=conversation["id"],
            role="assistant",
            content="中东正在阿拔斯革命后的权力整合期。",
            parent_message_id=user_message.message_id,
        )
        chat_service.add_artifacts(
            assistant_message["id"],
            {
                "event": [{"id": "evt-1", "title": "阿拔斯革命"}],
                "reference": [{"id": "ref-1", "title": "资料"}],
                "link": [{"type": "trace", "href": "https://example.test"}],
            },
        )

        owner_messages = chat_service.list_messages(owner["id"], conversation["id"])

        self.assertEqual(len(owner_messages), 2)
        self.assertEqual(owner_messages[1]["artifacts"]["event"][0]["title"], "阿拔斯革命")
        self.assertIsNone(chat_service.get_conversation(other["id"], conversation["id"]))
        with self.assertRaises(ValueError):
            chat_service.list_messages(other["id"], conversation["id"])

    def test_auth_cookie_allows_chat_api_access(self) -> None:
        suffix = uuid4().hex[:10]
        username = f"api_{suffix}"
        client = TestClient(app)

        register_response = client.post(
            "/auth/register",
            json={"username": username, "password": "secret123"},
        )
        self.assertEqual(register_response.status_code, 200)

        login_response = client.post(
            "/auth/login",
            json={"username": username, "password": "secret123"},
        )
        self.assertEqual(login_response.status_code, 200)

        me_response = client.get("/auth/me")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["user"]["username"], username)

        group_response = client.post("/chat/groups", json={"title": "测试分组"})
        self.assertEqual(group_response.status_code, 200)
        group_id = group_response.json()["group"]["id"]

        conversation_response = client.post(
            "/chat/conversations",
            json={"title": "测试会话", "group_id": group_id},
        )
        self.assertEqual(conversation_response.status_code, 200)
        conversation_id = conversation_response.json()["conversation"]["id"]

        message_response = client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"content": "你好"},
        )
        self.assertEqual(message_response.status_code, 200)

        detail_response = client.get(f"/chat/conversations/{conversation_id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(len(detail_response.json()["messages"]), 1)

    def test_memory_summary_recall_and_user_scope(self) -> None:
        suffix = uuid4().hex[:10]
        owner = auth_service.register(
            username=f"memory_owner_{suffix}",
            password="secret123",
        )
        other = auth_service.register(
            username=f"memory_other_{suffix}",
            password="secret123",
        )
        conversation = chat_service.create_conversation(owner["id"], title="安史之乱研究")
        user_message = chat_service.store_user_message(
            owner["id"],
            "我长期关注唐代和中亚的互动，尤其是安史之乱。",
            conversation_id=conversation["id"],
        )
        chat_service.create_message(
            user_id=owner["id"],
            conversation_id=conversation["id"],
            role="assistant",
            content="可以从唐朝、阿拔斯和中亚交通线三个角度比较。",
            parent_message_id=user_message.message_id,
        )

        result = memory_service.summarize_conversation(
            owner["id"],
            conversation["id"],
            create_memory_candidate=True,
        )

        self.assertIn("本会话共 2 条有效消息", result["summary"]["summary"])
        self.assertIsNotNone(result["memory_candidate"])
        self.assertEqual(result["memory_candidate"]["status"], "candidate")

        memory = memory_service.create_memory(
            owner["id"],
            "用户偏好把唐代事件放到中亚和中东背景里比较。",
            memory_type="preference",
            source_conversation_id=conversation["id"],
            source_summary_id=result["summary"]["id"],
        )
        recalled = memory_service.recall(owner["id"], "唐代中亚比较", limit=3)

        self.assertEqual(recalled[0]["id"], memory["id"])
        self.assertEqual(memory_service.recall(other["id"], "唐代中亚比较"), [])

        disabled = memory_service.update_memory(
            owner["id"],
            memory["id"],
            {"status": "disabled"},
        )
        self.assertEqual(disabled["status"], "disabled")
        self.assertEqual(memory_service.recall(owner["id"], "唐代中亚比较"), [])

    def test_memory_api_requires_auth_and_allows_user_control(self) -> None:
        suffix = uuid4().hex[:10]
        username = f"memory_api_{suffix}"
        client = TestClient(app)

        unauthorized = client.get("/memory/memories")
        self.assertEqual(unauthorized.status_code, 401)

        self.assertEqual(
            client.post("/auth/register", json={"username": username, "password": "secret123"}).status_code,
            200,
        )
        self.assertEqual(
            client.post("/auth/login", json={"username": username, "password": "secret123"}).status_code,
            200,
        )

        create_response = client.post(
            "/memory/memories",
            json={
                "content": "用户偏好按地区对照历史事件。",
                "memory_type": "preference",
                "confidence": 0.8,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        memory_id = create_response.json()["memory"]["id"]

        recall_response = client.get("/memory/recall", params={"query": "地区对照"})
        self.assertEqual(recall_response.status_code, 200)
        self.assertEqual(recall_response.json()["memories"][0]["id"], memory_id)

        delete_response = client.delete(f"/memory/memories/{memory_id}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["memory"]["status"], "deleted")


if __name__ == "__main__":
    unittest.main()
