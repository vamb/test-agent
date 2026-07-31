import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.dependencies import auth_service, chat_service
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


if __name__ == "__main__":
    unittest.main()
