param(
    [string]$TaskName = "BeautyGO-Respaldo-MySQL"
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$runner = Join-Path $projectRoot "ejecutar_respaldo.py"
$python = (Get-Command python.exe -ErrorAction Stop).Source

if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "No se encontró el ejecutor: $runner"
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "configuracion_entorno.py") -PathType Leaf)) {
    throw "Copia configuracion_entorno.example.py como configuracion_entorno.py y completa sus valores antes de programar la tarea."
}
$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "`"$runner`"" `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At "9:00 PM"
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Respaldo diario comprimido y cifrado de la base MySQL BeautyGO a Backblaze B2." `
    -Force | Out-Null

Write-Host "Tarea '$TaskName' registrada diariamente a las 21:00 (hora local de Windows)."
Write-Host "Confirma que la zona horaria de Windows sea Santiago con ajuste automatico de horario de verano y que Python, mysqldump y gpg esten en PATH."
