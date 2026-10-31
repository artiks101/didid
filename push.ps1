Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Pushing bot updates to GitHub (artiks101/didid)..." -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

$msg = Read-Host "Commit message (Press Enter for auto-date)"
if ([string]::IsNullOrWhiteSpace($msg)) {
    $msg = "Update bot: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}

git add .
git commit -m "$msg"
git push -u origin main

Write-Host "Done!" -ForegroundColor Green
