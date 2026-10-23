import os
import tempfile
import unittest
from unittest.mock import patch

import app as task_app


class TaskAppTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        task_app.app.config.update(
            TESTING=True,
            DATABASE=os.path.join(self.temp_dir.name, "tasks.sqlite3"),
        )
        task_app.init_db()
        self.client = task_app.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_task(self, title="要件確認", **values):
        data = {
            "title": title,
            "detail": "仕様を確認する",
            "assignee": "山田",
            "priority": "高",
            "status": "未着手",
            "due_date": "2026-10-30",
        }
        data.update(values)
        return self.client.post("/tasks", data=data, follow_redirects=True)

    def test_create_filter_edit_complete_comment_and_delete(self):
        response = self.create_task()
        self.assertIn("要件確認".encode(), response.data)
        self.assertIn("山田".encode(), self.client.get("/?q=山田&priority=高").data)

        with task_app.app.app_context(), task_app.get_db() as connection:
            task_id = connection.execute("SELECT id FROM tasks").fetchone()["id"]
        response = self.client.post(
            f"/tasks/{task_id}/edit",
            data={
                "title": "要件確認",
                "detail": "更新済み",
                "assignee": "山田",
                "priority": "高",
                "status": "完了",
                "due_date": "2026-10-30",
            },
            follow_redirects=True,
        )
        self.assertIn("完了日時".encode(), response.data)
        self.client.post(f"/tasks/{task_id}/comments", data={"body": "レビュー依頼済み"})
        self.assertIn("レビュー依頼済み".encode(), self.client.get(f"/?task={task_id}").data)
        with task_app.app.app_context():
            completed_at = task_app.get_task(task_id)["completed_at"]
        self.assertTrue(completed_at)
        self.client.post(f"/tasks/{task_id}/delete")
        self.assertNotIn("要件確認".encode(), self.client.get("/").data)

    def test_dashboard_totals_and_invalid_input(self):
        self.create_task(status="進行中")
        page = self.client.get("/")
        self.assertIn(b"1", page.data)
        invalid = self.client.post(
            "/tasks",
            data={"title": "", "priority": "高", "status": "未着手"},
            follow_redirects=True,
        )
        self.assertIn("タスク名を入力してください".encode(), invalid.data)

    def test_ai_input_limit_is_enforced_without_api_key(self):
        response = self.client.post("/api/ai/create", json={"text": "あ" * 2001})
        self.assertEqual(response.status_code, 400)
        self.assertIn("2000文字以内", response.get_json()["error"])

    def test_gemini_retries_503_and_limits_response(self):
        class UnavailableError(Exception):
            code = 503

        class Response:
            text = "回答" * 3000

        client = unittest.mock.MagicMock()
        client.models.generate_content.side_effect = [UnavailableError(), Response()]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "requested-model"}):
            with patch("google.genai.Client", return_value=client):
                result = task_app.gemini_generate("短い入力", "回答してください")
        self.assertEqual(len(result), 5000)
        self.assertEqual(
            [call.kwargs["model"] for call in client.models.generate_content.call_args_list],
            ["requested-model", "gemini-3.8-flash"],
        )

    def test_due_date_range_filter(self):
        self.create_task("今週のタスク")
        response = self.client.get("/?due_from=2026-10-29&due_to=2026-10-31")
        self.assertIn("今週のタスク".encode(), response.data)
        response = self.client.get("/?due_to=2026-10-29")
        self.assertNotIn("今週のタスク".encode(), response.data)

    def test_priority_sort_and_persisted_data(self):
        self.create_task("低優先度", priority="低")
        self.create_task("高優先度", priority="高")
        with task_app.app.app_context():
            tasks = task_app.fetch_tasks(task_app.current_filters({"sort": "priority"}))
        self.assertEqual([task["title"] for task in tasks], ["高優先度", "低優先度"])
        self.assertIn("高優先度".encode(), self.client.get("/").data)


if __name__ == "__main__":
    unittest.main()
