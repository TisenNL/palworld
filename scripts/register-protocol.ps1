# Registers palchecklist:// so the browser Start button can launch start.bat
$ErrorActionPreference = "SilentlyContinue"
$scripts = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scripts
$bat = Join-Path $root "start.bat"
$cmd = '"' + $bat + '" "%1"'

New-Item -Path "HKCU:\Software\Classes\palchecklist" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Classes\palchecklist" -Name "(default)" -Value "URL:Palworld Checklist Protocol"
New-ItemProperty -Path "HKCU:\Software\Classes\palchecklist" -Name "URL Protocol" -Value "" -PropertyType String -Force | Out-Null
New-Item -Path "HKCU:\Software\Classes\palchecklist\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Classes\palchecklist\shell\open\command" -Name "(default)" -Value $cmd
Write-Host "Registered palchecklist:// -> $bat"
