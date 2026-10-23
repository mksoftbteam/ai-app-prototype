import sys

from app import gemini_generate

if len(sys.argv) < 2:
    raise SystemExit("使い方: python test_gemini.py 'Geminiに送る入力' (2000文字以内)")

print(gemini_generate(" ".join(sys.argv[1:]), "入力に対して簡潔に回答してください。"))