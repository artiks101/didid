Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Отправка обновлений бота на GitHub (artiks101/didid)..." -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

$msg = Read-Host "Комментарий к коммиту (нажмите Enter для авто-даты)"
if ([string]::IsNullOrWhiteSpace($msg)) {
    $msg = "Update bot: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}

git add .
git commit -m "$msg"
git push -u origin main

Write-Host "`n✅ Готово!" -ForegroundColor Green
