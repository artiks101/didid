@echo off
chcp 65001 > nul
title Discord Admin Logger Bot
echo ===================================================
echo Запуск Discord Security & Moderation Logger...
echo ===================================================
python -m bot.main
pause
