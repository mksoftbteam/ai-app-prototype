# TALLY タスク管理アプリ

タスクの登録、進捗管理、検索を行う Flask 製のタスク管理アプリです。データは SQLite に保存され、アプリを再起動しても保持されます。

## 主な機能

- タスクの登録、一覧、詳細表示、編集、削除
- ステータス管理（未着手、進行中、保留、完了）
- タスク名、担当者、ステータス、優先度を対象にした検索
- 完了日時と更新日時の記録
- タスク名、詳細、期限日、優先度、担当者の管理

## 起動方法

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

ブラウザーで `http://localhost:5000` を開きます。DB は初回起動時に `instance/tasks.sqlite3` として作成されます。保存先は `TASKS_DATABASE` 環境変数で変更できます。

## 技術

- Python / Flask
- SQLite
- Jinja2

Gemini 用のプロンプトと `test_gemini.py` はプロジェクトに残しています。タスク管理アプリの起動には Gemini API キーは不要です。
