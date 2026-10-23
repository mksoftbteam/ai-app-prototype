import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, url_for

app = Flask(__name__)
app.config["DATABASE"] = os.environ.get(
    "TASK_DATABASE", str(Path(app.instance_path) / "tasks.sqlite3")
)

STATUSES = ("未着手", "進行中", "保留", "完了")
PRIORITIES = ("高", "中", "低")
PRIORITY_ORDER = "CASE priority WHEN '高' THEN 3 WHEN '中' THEN 2 ELSE 1 END"
SORT_COLUMNS = {
    "created_at": "created_at",
    "updated_at": "updated_at",
    "due_date": "due_date",
    "priority": PRIORITY_ORDER,
}


def now_iso():
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


@contextmanager
def get_db():
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(app.config["DATABASE"])
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    with get_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                due_date TEXT,
                priority TEXT NOT NULL DEFAULT '中',
                assignee TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '未着手',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def get_task(task_id):
    with get_db() as connection:
        task = connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    if task is None:
        abort(404)
    return dict(task)


def task_values(form):
    title = form.get("title", "").strip()
    priority = form.get("priority", "中")
    status = form.get("status", "未着手")
    due_date = form.get("due_date", "").strip() or None
    if not title:
        return None, "タスク名を入力してください。"
    if len(title) > 120:
        return None, "タスク名は120文字以内で入力してください。"
    if len(form.get("detail", "").strip()) > 2000:
        return None, "タスク詳細は2000文字以内で入力してください。"
    if priority not in PRIORITIES or status not in STATUSES:
        return None, "優先度またはステータスの値が不正です。"
    if due_date:
        try:
            datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            return None, "期限日を正しい形式で入力してください。"
    return {
        "title": title,
        "detail": form.get("detail", "").strip(),
        "due_date": due_date,
        "priority": priority,
        "assignee": form.get("assignee", "").strip()[:80],
        "status": status,
    }, None


def current_filters(args):
    return {
        "q": args.get("q", "").strip(),
        "status": args.get("status", ""),
        "priority": args.get("priority", ""),
        "due_date": args.get("due_date", ""),
        "due_from": args.get("due_from", ""),
        "due_to": args.get("due_to", ""),
        "assignee": args.get("assignee", "").strip(),
        "sort": args.get("sort", "created_at"),
        "direction": args.get("direction", "desc"),
    }


def fetch_tasks(filters):
    clauses = []
    values = []
    if filters["q"]:
        pattern = f"%{filters['q']}%"
        clauses.append("(title LIKE ? OR assignee LIKE ? OR status LIKE ? OR priority LIKE ?)")
        values.extend([pattern] * 4)
    if filters["status"] in STATUSES:
        clauses.append("status = ?")
        values.append(filters["status"])
    if filters["priority"] in PRIORITIES:
        clauses.append("priority = ?")
        values.append(filters["priority"])
    if filters["due_date"]:
        clauses.append("due_date = ?")
        values.append(filters["due_date"])
    if filters["due_from"]:
        clauses.append("due_date >= ?")
        values.append(filters["due_from"])
    if filters["due_to"]:
        clauses.append("due_date <= ?")
        values.append(filters["due_to"])
    if filters["assignee"]:
        clauses.append("assignee LIKE ?")
        values.append(f"%{filters['assignee']}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sort_column = SORT_COLUMNS.get(filters["sort"], "created_at")
    direction = "ASC" if filters["direction"] == "asc" else "DESC"
    with get_db() as connection:
        rows = connection.execute(
            f"SELECT * FROM tasks {where} ORDER BY {sort_column} {direction}, id DESC",
            values,
        ).fetchall()
    return [dict(row) for row in rows]


def dashboard_counts():
    with get_db() as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM tasks GROUP BY status"
        ).fetchall()
    counts = {status: 0 for status in STATUSES}
    counts.update({row["status"]: row["count"] for row in rows})
    counts["total"] = sum(counts.values())
    return counts


def compact_task_context(tasks, limit=1100):
    compact = []
    for task in tasks:
        item = {
            key: str(task.get(key) or "")[:100]
            for key in ("title", "detail", "assignee", "priority", "status", "due_date", "updated_at")
        }
        candidate = json.dumps(compact + [item], ensure_ascii=False)
        if len(candidate) > limit:
            break
        compact.append(item)
    return json.dumps(compact, ensure_ascii=False)


@app.route("/", methods=["GET"])
def index():
    filters = current_filters(request.args)
    tasks = fetch_tasks(filters)
    selected = get_task(int(request.args["task"])) if request.args.get("task", "").isdigit() else None
    comments = []
    if selected:
        with get_db() as connection:
            comments = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM comments WHERE task_id = ? ORDER BY id DESC",
                    (selected["id"],),
                ).fetchall()
            ]
    return render_template(
        "index.html",
        tasks=tasks,
        counts=dashboard_counts(),
        filters=filters,
        selected=selected,
        comments=comments,
        statuses=STATUSES,
        priorities=PRIORITIES,
        error=request.args.get("error", ""),
    )


@app.post("/tasks")
def create_task():
    values, error = task_values(request.form)
    if error:
        return redirect(url_for("index", error=error)), 303
    timestamp = now_iso()
    completed_at = timestamp if values["status"] == "完了" else None
    with get_db() as connection:
        connection.execute(
            """INSERT INTO tasks
            (title, detail, due_date, priority, assignee, status, created_at, updated_at, completed_at)
            VALUES (:title, :detail, :due_date, :priority, :assignee, :status, :created_at, :updated_at, :completed_at)""",
            {**values, "created_at": timestamp, "updated_at": timestamp, "completed_at": completed_at},
        )
    return redirect(url_for("index"), code=303)


@app.post("/tasks/<int:task_id>/edit")
def edit_task(task_id):
    existing = get_task(task_id)
    values, error = task_values(request.form)
    if error:
        return redirect(url_for("index", task=task_id, error=error)), 303
    timestamp = now_iso()
    completed_at = existing["completed_at"]
    if values["status"] == "完了" and existing["status"] != "完了":
        completed_at = timestamp
    elif values["status"] != "完了":
        completed_at = None
    with get_db() as connection:
        connection.execute(
            """UPDATE tasks SET title=:title, detail=:detail, due_date=:due_date,
            priority=:priority, assignee=:assignee, status=:status,
            updated_at=:updated_at, completed_at=:completed_at WHERE id=:id""",
            {**values, "updated_at": timestamp, "completed_at": completed_at, "id": task_id},
        )
    return redirect(url_for("index", task=task_id), code=303)


@app.post("/tasks/<int:task_id>/delete")
def delete_task(task_id):
    get_task(task_id)
    with get_db() as connection:
        connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return redirect(url_for("index"), code=303)


@app.post("/tasks/<int:task_id>/comments")
def add_comment(task_id):
    get_task(task_id)
    body = request.form.get("body", "").strip()
    if body:
        with get_db() as connection:
            connection.execute(
                "INSERT INTO comments (task_id, body, created_at) VALUES (?, ?, ?)",
                (task_id, body[:2000], now_iso()),
            )
    return redirect(url_for("index", task=task_id), code=303)


def gemini_generate(user_input, instruction):
    text = str(user_input or "").strip()
    if not text:
        raise ValueError("AIへの入力を入力してください。")
    if len(text) > 2000:
        raise ValueError("AIへの入力は2000文字以内で入力してください。")
    prompt_path = Path(__file__).parent / "prompts" / "system_prompt.txt"
    system_prompt = prompt_path.read_text(encoding="utf-8")
    prompt = f"{system_prompt}\n\n{instruction}\n\n入力:\n{text}"[:2000]
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEYが設定されていません。")
    from google import genai

    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
    try:
        response = client.models.generate_content(model=model, contents=prompt)
    except Exception as error:
        status_code = getattr(error, "code", None) or getattr(error, "status_code", None)
        if status_code != 503 and "503" not in str(error):
            raise
        response = client.models.generate_content(model="gemini-3.8-flash", contents=prompt)
    return str(getattr(response, "text", "") or "AIから回答がありませんでした。")[:5000]


def parse_ai_json(text):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("AIの回答を読み取れませんでした。もう一度お試しください。")
    return json.loads(cleaned[start : end + 1])


@app.post("/api/ai/<action>")
def ai_action(action):
    payload = request.get_json(silent=True) or {}
    try:
        if action == "create":
            text = gemini_generate(
                payload.get("text"),
                "自然文からタスクを抽出し、title, detail, due_date(YYYY-MM-DDまたは空文字), assignee, priority(高/中/低), status(未着手/進行中/保留/完了)のJSONだけを返してください。日付が不明なら空文字にしてください。",
            )
            result = parse_ai_json(text)
            result["priority"] = result.get("priority") if result.get("priority") in PRIORITIES else "中"
            result["status"] = result.get("status") if result.get("status") in STATUSES else "未着手"
            result["title"] = str(result.get("title", ""))[:120]
            return jsonify(result)
        if action == "search":
            text = gemini_generate(
                payload.get("text"),
                f"自然文検索をJSONに変換してください。statusは{STATUSES}、priorityは{PRIORITIES}、due_fromとdue_toはYYYY-MM-DDか空文字、assigneeは文字列。JSONだけ返してください。今日の日付は{datetime.now().date().isoformat()}です。",
            )
            result = parse_ai_json(text)
            return jsonify({key: result.get(key, "") for key in ("status", "priority", "due_from", "due_to", "assignee")})
        if action in {"priority", "progress"}:
            task = get_task(int(payload.get("task_id", 0)))
            with get_db() as connection:
                notes = connection.execute(
                    "SELECT body, created_at FROM comments WHERE task_id = ? ORDER BY id DESC LIMIT 20",
                    (task["id"],),
                ).fetchall()
            task_context = compact_task_context(
                [{**task, "detail": task["detail"][:300]}]
                + [{"title": "コメント", "detail": note["body"][:100], "updated_at": note["created_at"]} for note in notes[:5]],
                1000,
            )
            instruction = "期限・内容・状態・更新日時を根拠に優先度(高/中/低)と理由を提案してください。" if action == "priority" else "期限超過リスク、停滞状況、完了見込みを簡潔に分析してください。"
            return jsonify({"analysis": gemini_generate(task_context, instruction)})
        if action == "dashboard":
            task_context = compact_task_context(fetch_tasks(current_filters({})))
            return jsonify({"analysis": gemini_generate(task_context, "タスク状況を分析し、完了率・遅延率・担当者別件数・優先度別件数・ステータス別件数に触れて、具体的な次の行動を提案してください。")})
        if action == "chat":
            text = payload.get("text", "")
            if len(str(text)) > 2000:
                raise ValueError("AIへの入力は2000文字以内で入力してください。")
            question = str(text).strip()
            context_limit = max(0, min(1000, 1900 - len(question)))
            task_context = compact_task_context(fetch_tasks(current_filters({})), context_limit)
            chat_input = f"質問: {question}\n登録済みタスク: {task_context}"[:2000]
            return jsonify({"answer": gemini_generate(chat_input, "登録済みタスク情報に基づいて日本語で回答してください。不明な情報は推測しないでください。")})
        return jsonify({"error": "未対応のAI機能です。"}), 404
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.exception("Gemini request failed")
        return jsonify({"error": str(error)[:300]}), 502


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
