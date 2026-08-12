$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$container = "knowledge-neo4j-test-$PID"
$password = "phase6-integration-test-password"

try {
    docker run --rm -d `
        --name $container `
        -p 17474:7474 `
        -p 17687:7687 `
        -e "NEO4J_AUTH=neo4j/$password" `
        neo4j:5.4.0-community | Out-Null

    $env:TEST_NEO4J_ISOLATED = "1"
    $env:TEST_NEO4J_URI = "bolt://127.0.0.1:17687"
    $env:TEST_NEO4J_USER = "neo4j"
    $env:TEST_NEO4J_PASSWORD = $password
    $env:TEST_NEO4J_DATABASE = "neo4j"
    & (Join-Path $root ".venv\Scripts\python.exe") `
        -m pytest -m integration -v
    if ($LASTEXITCODE -ne 0) {
        throw "Neo4j integration tests failed with exit code $LASTEXITCODE"
    }
}
finally {
    docker stop $container 2>$null | Out-Null
}
