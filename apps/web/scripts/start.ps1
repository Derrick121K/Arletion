param(
  [ValidateRange(1, 65535)]
  [int]$Port = 3000
)

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
  foreach ($listener in $listeners) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
    [PSCustomObject]@{
      Port = $Port
      PID = $listener.OwningProcess
      Process = $process.Name
      CommandLine = $process.CommandLine
    } | Format-List
  }
  Write-Error "Port $Port is occupied. Inspect the PID and command above. Stop only a confirmed Arletion process from its owning terminal, or retry with: npm run start:windows -- -Port 3001"
  exit 2
}

$env:PORT = "$Port"
npm run start
exit $LASTEXITCODE
