# 用任务计划程序安装每日任务。用法：powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1 [-Time 09:30]
# StartWhenAvailable：错过的任务在开机后补跑。
param([string]$Time = "09:30")

$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$Py = (Get-Command python -ErrorAction Stop).Source
if (-not (Test-Path "$Root\config.json")) { throw "先复制 config.example.json 为 config.json 并填写推送 key" }

$action = New-ScheduledTaskAction -Execute $Py -Argument "-m tracker run" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "MinigameTracker" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Output "已安装：每天 $Time 运行。立即试跑：Start-ScheduledTask -TaskName MinigameTracker"
