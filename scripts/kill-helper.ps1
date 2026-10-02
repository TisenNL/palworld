$pids = @()
Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^(python|py)\.exe$' -and $_.CommandLine -and ($_.CommandLine -match 'coord_tooltip\.py')
} | ForEach-Object {
  $pids += $_.ProcessId
  Write-Host ("KILL $($_.ProcessId)")
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

$port = if ($env:PALWORLD_PORT) { [int]$env:PALWORLD_PORT } else { 8765 }
Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
  $owner = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
  if (-not $owner) { return }
  # Só mata se for mesmo o helper (python). Qualquer outro serviço que use a
  # porta permanece intacto.
  if ($owner.Name -match '^(python|py)w?\d*(\.exe)?$') {
    Write-Host ("KILL port$port $($owner.Id) ($($owner.Name))")
    Stop-Process -Id $owner.Id -Force -ErrorAction SilentlyContinue
  } else {
    Write-Host ("SKIP port$port belongs to $($owner.Name) - not the helper")
  }
}

Start-Sleep -Seconds 1
$left = @(Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -and ($_.CommandLine -match 'coord_tooltip\.py') -and ($_.Name -match 'python|py')
})
Write-Host ("remaining=" + $left.Count)
