$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root "logs"
$neo4jHome = "C:\neo4j-community-5.4.0"
$python = Join-Path $root ".venv\Scripts\python.exe"
$backendDirectory = Join-Path $root "application\backend"
$frontendDirectory = Join-Path $root "application\frontend"
$vite = Join-Path $frontendDirectory "node_modules\vite\bin\vite.js"
$node = (Get-Command node.exe -ErrorAction Stop).Source

New-Item -ItemType Directory -Path $logs -Force | Out-Null

function Test-TcpPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(1000)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-TcpPort([int]$Port, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-TcpPort $Port) {
            return
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port did not become ready within $TimeoutSeconds seconds"
}

$processes = @()
try {
    if (-not (Test-TcpPort 7687)) {
        $neo4j = Start-Process `
            -FilePath "powershell.exe" `
            -ArgumentList @(
                "-NoProfile",
                "-File",
                (Join-Path $neo4jHome "bin\neo4j.ps1"),
                "console"
            ) `
            -WorkingDirectory $neo4jHome `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logs "acceptance-neo4j.out.log") `
            -RedirectStandardError (Join-Path $logs "acceptance-neo4j.err.log") `
            -PassThru
        $processes += $neo4j
        Wait-TcpPort 7687 60
    }

    $backend = Start-Process `
        -FilePath $python `
        -ArgumentList "main.py" `
        -WorkingDirectory $backendDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "acceptance-backend.out.log") `
        -RedirectStandardError (Join-Path $logs "acceptance-backend.err.log") `
        -PassThru
    $processes += $backend

    $frontend = Start-Process `
        -FilePath $node `
        -ArgumentList @($vite, "--host", "127.0.0.1", "--port", "5173") `
        -WorkingDirectory $frontendDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "acceptance-frontend.out.log") `
        -RedirectStandardError (Join-Path $logs "acceptance-frontend.err.log") `
        -PassThru
    $processes += $frontend

    Wait-TcpPort 8000 60
    Wait-TcpPort 5173 60

    [pscustomobject]@{
        started_at = (Get-Date).ToString("o")
        neo4j_pid = (Get-NetTCPConnection -State Listen -LocalPort 7687).OwningProcess
        backend_pid = $backend.Id
        frontend_pid = $frontend.Id
    } | ConvertTo-Json | Set-Content `
        -LiteralPath (Join-Path $logs "acceptance-stack.json") `
        -Encoding UTF8

    while ($true) {
        Start-Sleep -Seconds 2
        if ($backend.HasExited -or $frontend.HasExited -or -not (Test-TcpPort 7687)) {
            break
        }
    }
}
finally {
    foreach ($process in $processes) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
