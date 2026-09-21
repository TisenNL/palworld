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
  Write-Host ("KILL port8765 $($_.OwningProcess)")
  Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 1
$left = @(Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -and ($_.CommandLine -match 'coord_tooltip\.py') -and ($_.Name -match 'python|py')
})
Write-Host ("remaining=" + $left.Count)
