@echo off
cd /d "%~dp0"
chcp 65001 >nul
python -u -c "print('\u6b62\u3081\u308b\u3068\u304d\u306f\u3053\u306e\u7a93\u3092\u9589\u3058\u308b / Close this window to stop')"
python -u preview_articles.py
if errorlevel 1 pause
