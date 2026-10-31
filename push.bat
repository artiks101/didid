@echo off
chcp 65001 > nul
title Push to GitHub (artiks101/didid)
echo ===================================================
echo Отправка обновлений бота в GitHub: artiks101/didid
echo ===================================================

set /p msg="Комментарий к коммиту (или нажмите Enter): "
if "%msg%"=="" set msg=Update bot: %date% %time%

git add .
git commit -m "%msg%"
git push -u origin main

echo.
echo ===================================================
echo Завершено!
echo ===================================================
pause
