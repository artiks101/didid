@echo off
title Push to GitHub: artiks101/didid
echo ===================================================
echo Pushing bot updates to GitHub: artiks101/didid
echo ===================================================

git add .
git commit -m "Update bot files"
git push -u origin main

echo.
echo ===================================================
echo Done!
echo ===================================================
pause
