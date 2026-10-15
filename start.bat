@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запуск бота ESUfanetBet...
python run.py
echo.
echo Бот остановлен.
pause
