[CmdletBinding()]
param(
    [switch]$KeepNeo4j
)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $ProjectRoot ".runtime"
$ports = @(5173, 8600, 8000)
if (-not $KeepNeo4j) {
    $ports += @(7687, 7474)
}

$stopped = @{}
if (Test-Path -LiteralPath $RuntimeDir) {
    Get-ChildItem -LiteralPath $RuntimeDir -Filter "*.pid" -File | ForEach-Object {
        if ($KeepNeo4j -and $_.BaseName -eq "neo4j") {
            return
        }
        $managedPid = 0
        if (-not [int]::TryParse((Get-Content -LiteralPath $_.FullName -Raw).Trim(), [ref]$managedPid)) {
            Write-Warning "Ignoring invalid PID file: $($_.FullName)"
            return
        }
        $managedProcess = Get-Process -Id $managedPid -ErrorAction SilentlyContinue
        if (-not $managedProcess) { return }
        # A stale PID file must not stop a later unrelated process that reused the PID.
        if ($managedProcess.StartTime -lt $_.LastWriteTime.AddSeconds(-5)) {
            Write-Warning "Ignoring stale PID file for PID $managedPid"
            return
        }
        Stop-Process -Id $managedPid -Force
        $stopped[$managedPid] = $true
        Write-Host "[stopped] managed PID $managedPid"
    }
    Start-Sleep -Milliseconds 500
}

foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $processId = $connection.OwningProcess
        if ($stopped.ContainsKey($processId)) { continue }
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
        $commandLine = [string]$processInfo.CommandLine
        $isProjectProcess = $commandLine.IndexOf($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        $isNeo4jProcess = $port -in 7474, 7687 -and $commandLine -match 'neo4j'
        if (-not $isProjectProcess -and -not $isNeo4jProcess) {
            Write-Warning "Not stopping PID $processId on $port because it is not owned by this stack."
            continue
        }
        Stop-Process -Id $processId -Force
        $stopped[$processId] = $true
        Write-Host "[stopped] PID $processId on $port"
    }
}

if (Test-Path -LiteralPath $RuntimeDir) {
    Get-ChildItem -LiteralPath $RuntimeDir -Filter "*.pid" -File | Remove-Item -Force
}
