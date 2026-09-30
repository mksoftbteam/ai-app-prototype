import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from flask import Flask, abort, redirect, render_template, request, url_for

app = Flask(__name__)
app.config["DATABASE"] = os.environ.get(
    "TASKS_DATABASE",
    os.path.join(app.instance_path, "tasks.sqlite3"),
)

STATUSES = ("未着手", "進行中", "保留", "完了")
PRIORITIES = ("高", "中", "低")


def get_db():
    connection = sqlite3.connect(app.config["DATABASE"])
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def db_connection():
    connection = get_db()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db():
    database_dir = os.path.dirname(os.path.abspath(app.config["DATABASE"]))
    os.makedirs(database_dir, exist_ok=True)
    with db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                due_date TEXT,
                priority TEXT NOT NULL,
                assignee TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )


def get_task(task_id):
    with db_connection() as connection:
        task = connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    if task is None:
        abort(404)
    return task


def task_values(form):
    return {
        "title": form.get("title", "").strip(),
        "details": form.get("details", "").strip(),
        "due_date": form.get("due_date", "").strip(),
        "priority": form.get("priority", ""),
        "assignee": form.get("assignee", "").strip(),
        "status": form.get("status", ""),
    }


def validate_task(values):
    if not values["title"]:
        return "タスク名を入力してください。"
    if values["priority"] not in PRIORITIES:
        return "優先度を選択してください。"
    if values["status"] not in STATUSES:
        return "ステータスを選択してください。"
    if values["due_date"]:
        try:
            datetime.strptime(values["due_date"], "%Y-%m-%d")
        except ValueError:
            return "期限日を正しく入力してください。"
    return None


@app.route("/")
def index():
    query = request.args.get("q", "").strip()
    with db_connection() as connection:
        if query:
            wildcard = f"%{query}%"
            tasks = connection.execute(
                """SELECT * FROM tasks
                   WHERE title LIKE ? OR assignee LIKE ?
                      OR status LIKE ? OR priority LIKE ?
                   ORDER BY updated_at DESC, id DESC""",
                (wildcard, wildcard, wildcard, wildcard),
            ).fetchall()
        else:
            tasks = connection.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC, id DESC"
            ).fetchall()
    return render_template("index.html", tasks=tasks, query=query)


@app.route("/tasks/new", methods=["GET", "POST"])
def create_task():
    values = {
        "title": "",
        "details": "",
        "due_date": "",
        "priority": "中",
        "assignee": "",
        "status": "未着手",
    }
    error = None
    if request.method == "POST":
        values = task_values(request.form)
        error = validate_task(values)
        if error is None:
            now = datetime.now().isoformat(timespec="seconds")
            completed_at = now if values["status"] == "完了" else None
            with db_connection() as connection:
                cursor = connection.execute(
                    """INSERT INTO tasks
                       (title, details, due_date, priority, assignee, status,
                        created_at, updated_at, completed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        values["title"], values["details"],
                        values["due_date"] or None, values["priority"],
                        values["assignee"], values["status"], now, now,
                        completed_at,
                    ),
                )
                task_id = cursor.lastrowid
            return redirect(url_for("task_detail", task_id=task_id))
    return render_template(
        "index.html", page="form", mode="new", task=values, error=error,
        statuses=STATUSES, priorities=PRIORITIES,
    )


@app.route("/tasks/<int:task_id>")
def task_detail(task_id):
    return render_template("index.html", page="detail", task=get_task(task_id))


@app.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
def edit_task(task_id):
    task = get_task(task_id)
    error = None
    if request.method == "POST":
        values = task_values(request.form)
        error = validate_task(values)
        if error is None:
            now = datetime.now().isoformat(timespec="seconds")
            if values["status"] == "完了":
                completed_at = task["completed_at"] or now
            else:
                completed_at = None
            with db_connection() as connection:
                connection.execute(
                    """UPDATE tasks SET title = ?, details = ?, due_date = ?,
                       priority = ?, assignee = ?, status = ?, updated_at = ?,
                       completed_at = ? WHERE id = ?""",
                    (
                        values["title"], values["details"],
                        values["due_date"] or None, values["priority"],
                        values["assignee"], values["status"], now,
                        completed_at, task_id,
                    ),
                )
            return redirect(url_for("task_detail", task_id=task_id))
        task = {**values, "id": task_id}
    return render_template(
        "index.html", page="form", mode="edit", task=task, error=error,
        statuses=STATUSES, priorities=PRIORITIES,
    )


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id):
    get_task(task_id)
    with db_connection() as connection:
        connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return redirect(url_for("index"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)