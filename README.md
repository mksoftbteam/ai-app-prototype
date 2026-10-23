# Taskline タスク管理アプリ

FlaskとSQLiteでタスクを管理し、Gemini APIで作成・検索・優先度提案・進捗分析を支援するWebアプリです。

## 機能

- タスクの登録、一覧、詳細、編集、削除とステータス管理
- ステータス・優先度・期限日・担当者での絞り込み、キーワード検索、作成日・更新日・期限日・優先度の並べ替え
- 完了日時の記録、作業コメント、ステータス別ダッシュボード
- Geminiによる自然文タスク作成・検索、タスク優先度提案、進捗分析、ダッシュボード分析、チャット
- SQLiteによるデータ永続化（既定: `instance/tasks.sqlite3`）

## 起動

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY="your-api-key"
python app.py
```

ブラウザーで `http://localhost:5000` を開きます。Gemini機能を利用しない場合、APIキーなしでもタスク管理機能を利用できます。

## 設定

- `GEMINI_API_KEY`: Gemini APIキー（AI機能の利用時に必要）
- `GEMINI_MODEL`: 指定モデル。既定値は `gemini-3.6-flash`。503の場合は `gemini-3.8-flash` で1回再試行します。
- `TASK_DATABASE`: SQLiteファイルの保存先。未指定時は `instance/tasks.sqlite3`
- `PORT`: Webサーバーのポート。未指定時は `5000`

Geminiへの入力は2000文字以内、アプリが返すAI出力は5000文字以内です。

## テスト

```bash
python -m unittest -v test_app
```
