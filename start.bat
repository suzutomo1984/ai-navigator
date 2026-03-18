@echo off
cd /d "%~dp0\.."
echo 最新データを取得中...
git pull
cd ai-news-hub
echo AI NEWS HUB 起動中...
python parse_news.py
start http://localhost:8080
python -m http.server 8080
