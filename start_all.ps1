[CmdletBinding()]
param(
    [string]$Neo4jHome = $env:NEO4J_HOME,
    [switch]$SkipGraphFrontend
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $ProjectRoot ".runtime"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$GraphBackendDir = Join-Path $ProjectRoot "graph\application\backend"
$GraphFrontendDir = Join-Path $ProjectRoot "graph\application\frontend"

if ([string]::IsNullOrWhiteSpace($Neo4jHome)) {
    $Neo4jHome = "C:\neo4j-community-5.4.0"
}

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

function Test-ListeningPort {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Wait-ListeningPort {
    param([int]$Port, [int]$TimeoutSeconds = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-ListeningPort $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Wait-HttpEndpoint {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 60,
        [string]$Accept = "application/json"
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest `
                -Uri $Uri `
                -UseBasicParsing `
                -TimeoutSec 5 `
                -Headers @{ Accept = $Accept }
            if ($response.StatusCode -eq 200) { return $true }
        } catch {
            Start-Sleep -Milliseconds 500
            continue
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function ConvertTo-ProcessArgument {
    param([AllowEmptyString()][string]$Value)
    if ($Value.Contains('"')) {
        throw "Process arguments containing quotes are not supported: $Value"
    }
    return '"' + $Value + '"'
}

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [int]$Port,
        [int]$TimeoutSeconds = 60
    )
    if (Test-ListeningPort $Port) {
        Write-Host "[reuse] $Name is already listening on $Port"
        return
    }

    $stdoutPath = Join-Path $RuntimeDir "$Name.stdout.log"
    $stderrPath = Join-Path $RuntimeDir "$Name.stderr.log"
    $commandParts = @((ConvertTo-ProcessArgument $FilePath))
    $commandParts += $Arguments | ForEach-Object { ConvertTo-ProcessArgument $_ }
    $commandLine = ($commandParts -join ' ') +
        ' 1>' + (ConvertTo-ProcessArgument $stdoutPath) +
        ' 2>' + (ConvertTo-ProcessArgument $stderrPath)

    # Windows PowerShell's Start-Process merges environment variables into a
    # case-sensitive dictionary and can fail when Path/PATH casing differs.
    # Process.Start inherits the native environment block without that merge;
    # cmd.exe owns file redirection so the managed process can keep running.
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $env:ComSpec
    $startInfo.Arguments = '/d /s /c "' + $commandLine + '"'
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $process = [System.Diagnostics.Process]::Start($startInfo)
    Set-Content -LiteralPath (Join-Path $RuntimeDir "$Name.pid") -Value $process.Id

    if (-not (Wait-ListeningPort -Port $Port -TimeoutSeconds $TimeoutSeconds)) {
        throw "$Name failed to listen on $Port. See $stderrPath"
    }
    Write-Host "[ready] $Name on $Port (PID $($process.Id))"
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Missing Python environment: $PythonExe"
}

if (-not (Test-ListeningPort 7687)) {
    $javaExe = if (-not [string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
        Join-Path $env:JAVA_HOME "bin\java.exe"
    } else {
        (Get-Command java.exe -ErrorAction Stop).Source
    }
    if (-not (Test-Path -LiteralPath $javaExe)) {
        throw "Java launcher not found: $javaExe"
    }
    $neo4jLib = (Join-Path $Neo4jHome "lib\*")
    Start-ManagedProcess `
        -Name "neo4j" `
        -FilePath $javaExe `
        -Arguments @("-cp", $neo4jLib, "-Dbasedir=$Neo4jHome", "org.neo4j.server.startup.Neo4jCommand", "console") `
        -WorkingDirectory $Neo4jHome `
        -Port 7687 `
        -TimeoutSeconds 90
} else {
    Write-Host "[reuse] Neo4j is already listening on 7687"
}

$graphEnv = Join-Path $GraphBackendDir ".env"
if (-not (Test-Path -LiteralPath $graphEnv) -and -not (Select-String -LiteralPath (Join-Path $ProjectRoot ".env") -Pattern '^NEO4J_PASSWORD=.+' -Quiet -ErrorAction SilentlyContinue)) {
    throw "Set NEO4J_PASSWORD in the root .env or $graphEnv"
}

Start-ManagedProcess `
    -Name "graph-backend" `
    -FilePath $PythonExe `
    -Arguments @("-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $GraphBackendDir `
    -Port 8000
if (-not (Wait-HttpEndpoint -Uri "http://127.0.0.1:8000/health/ready")) {
    throw "Graph backend port is open but readiness check failed."
}

Start-ManagedProcess `
    -Name "tutor" `
    -FilePath $PythonExe `
    -Arguments @("web_server.py") `
    -WorkingDirectory $ProjectRoot `
    -Port 8600
if (-not (Wait-HttpEndpoint -Uri "http://127.0.0.1:8600/api/profile?student=startup_check")) {
    throw "Tutor port is open but HTTP check failed."
}

if (-not $SkipGraphFrontend) {
    $nodeModules = Join-Path $GraphFrontendDir "node_modules"
    if (-not (Test-Path -LiteralPath $nodeModules)) {
        throw "Missing frontend dependencies. Run: cd graph\application\frontend; npm ci"
    }
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    Start-ManagedProcess `
        -Name "graph-frontend" `
        -FilePath $npm `
        -Arguments @("run", "dev") `
        -WorkingDirectory $GraphFrontendDir `
        -Port 5173
    if (-not (Wait-HttpEndpoint -Uri "http://127.0.0.1:5173/" -Accept "text/html")) {
        throw "Graph frontend port is open but HTTP check failed."
    }
}

Write-Host ""
Write-Host "Tutor:          http://127.0.0.1:8600"
if (-not $SkipGraphFrontend) {
    Write-Host "Knowledge graph: http://127.0.0.1:5173"
}
Write-Host "Graph API:       http://127.0.0.1:8000/docs"
