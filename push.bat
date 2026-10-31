@echo off
chcp 65001 > nul
title Push to GitHub
echo ===================================================
echo Отправка обновлений бота в GitHub (artiks101/didid)
echo ===================================================

set /p msg="Комментарий к обновлению (Enter для 'update'): "
if "%msg%"=="" set msg=Update bot: %date% %time%

git add bot/ requirements.txt README.md .env.example .gitignore run.bat push.bat
git commit -m "%msg%"
git push origin main

echo.
echo ===================================================
echo Готово!
echo ===================================================
pause
