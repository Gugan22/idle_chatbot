param(
    [ValidateSet("up", "infra", "down", "restart", "logs", "status")]
    [string]$Action = "up"
)

# Akilu changed this because the complete local stack should run with native Podman commands only.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
$network = "idle-chatbot-net"
$apiImage = "localhost/idle-chatbot-api:local"
$containers = @("insurance-api", "insurance-ollama", "insurance-redis", "insurance-qdrant")

function Invoke-Podman {
    param([string[]]$Arguments)
    & podman @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Podman command failed: podman $($Arguments -join ' ')"
    }
}

function Get-ConfigValue {
    param([string]$Name, [string]$Default)
    $fromProcess = [Environment]::GetEnvironmentVariable($Name)
    if ($fromProcess) { return $fromProcess }
    if (Test-Path -LiteralPath $envFile) {
        $line = Get-Content -LiteralPath $envFile |
            Where-Object { $_ -match "^\s*$([regex]::Escape($Name))=(.*)$" } |
            Select-Object -Last 1
        if ($line -and $line -match "^\s*[^=]+=(.*)$") { return $Matches[1].Trim() }
    }
    return $Default
}

function Ensure-PodmanMachine {
    if (-not (Get-Command podman -ErrorAction SilentlyContinue)) {
        throw "Podman is not installed or is not available on PATH."
    }
    if (-not ($IsWindows -or $env:OS -eq "Windows_NT")) { return }

    $machineJson = podman machine list --format json
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to inspect the Podman machine. Check Podman permissions and connections."
    }
    $machine = $machineJson | ConvertFrom-Json | Select-Object -First 1
    if (-not $machine) {
        Invoke-Podman @("machine", "init")
        Invoke-Podman @("machine", "start")
        return
    }
    $isRunning = (
        $machine.Running -eq $true -or
        "$($machine.State)".ToLowerInvariant() -eq "running" -or
        "$($machine.Status)".ToLowerInvariant() -eq "running"
    )
    if (-not $isRunning) {
        Invoke-Podman @("machine", "start", $machine.Name)
    }
}

function Ensure-Network {
    & podman network exists $network
    if ($LASTEXITCODE -ne 0) { Invoke-Podman @("network", "create", $network) }
}

function Ensure-Volume {
    param([string]$Name)
    & podman volume exists $Name
    if ($LASTEXITCODE -ne 0) { Invoke-Podman @("volume", "create", $Name) }
}

function Ensure-ContainerStarted {
    param([string]$Name, [string[]]$RunArguments)
    & podman container exists $Name
    if ($LASTEXITCODE -eq 0) {
        Invoke-Podman @("start", $Name)
    }
    else {
        Invoke-Podman $RunArguments
    }
}

function Wait-ForCommand {
    param([string[]]$Arguments, [string]$Service, [int]$Attempts = 120)
    for ($i = 0; $i -lt $Attempts; $i++) {
        & podman @Arguments *> $null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 2
    }
    throw "$Service did not become ready."
}

function Wait-ForHttp {
    param([string]$Url, [string]$Service, [int]$Attempts = 120)
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 *> $null
            return
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "$Service did not become ready."
}

function Start-Infrastructure {
    Ensure-Network
    Ensure-Volume "idle-chatbot-qdrant"
    Ensure-Volume "idle-chatbot-redis"
    Ensure-Volume "idle-chatbot-ollama"

    $qdrantPort = Get-ConfigValue "QDRANT_PORT" "6333"
    $qdrantGrpcPort = Get-ConfigValue "QDRANT_GRPC_PORT" "6334"
    $redisPort = Get-ConfigValue "REDIS_PORT" "6379"
    $ollamaPort = Get-ConfigValue "OLLAMA_PORT" "11434"
    $qdrantImage = Get-ConfigValue "QDRANT_IMAGE" "docker.io/qdrant/qdrant:v1.12.5"
    $redisImage = Get-ConfigValue "REDIS_IMAGE" "docker.io/library/redis:7.4-alpine"
    $ollamaImage = Get-ConfigValue "OLLAMA_IMAGE" "docker.io/ollama/ollama:0.5.7"

    Ensure-ContainerStarted "insurance-qdrant" @(
        "run", "-d", "--name", "insurance-qdrant", "--network", $network,
        "--label", "io.idle-chatbot.stack=true",
        "-p", "127.0.0.1:${qdrantPort}:6333", "-p", "127.0.0.1:${qdrantGrpcPort}:6334",
        "-v", "idle-chatbot-qdrant:/qdrant/storage:U", $qdrantImage
    )
    Ensure-ContainerStarted "insurance-redis" @(
        "run", "-d", "--name", "insurance-redis", "--network", $network,
        "--label", "io.idle-chatbot.stack=true",
        "-p", "127.0.0.1:${redisPort}:6379", "-v", "idle-chatbot-redis:/data:U", $redisImage
    )
    Ensure-ContainerStarted "insurance-ollama" @(
        "run", "-d", "--name", "insurance-ollama", "--network", $network,
        "--label", "io.idle-chatbot.stack=true",
        "-p", "127.0.0.1:${ollamaPort}:11434", "-v", "idle-chatbot-ollama:/root/.ollama:U", $ollamaImage
    )

    Wait-ForHttp "http://127.0.0.1:$qdrantPort/healthz" "Qdrant"
    Wait-ForCommand @("exec", "insurance-redis", "redis-cli", "ping") "Redis"
    Wait-ForCommand @("exec", "insurance-ollama", "ollama", "list") "Ollama"
    Invoke-Podman @("exec", "insurance-ollama", "ollama", "pull", (Get-ConfigValue "LLM_MODEL" "phi3:latest"))
}

function Remove-StackContainers {
    foreach ($name in $containers) {
        & podman container exists $name
        if ($LASTEXITCODE -eq 0) { Invoke-Podman @("rm", "-f", $name) }
    }
}

function Start-CompleteStack {
    Start-Infrastructure
    Ensure-Volume "idle-chatbot-model-cache"
    Set-Location $root
    Invoke-Podman @("build", "-f", "Containerfile", "-t", $apiImage, ".")

    $collection = Get-ConfigValue "COLLECTION_NAME" "insurance_policies"
    $embedModel = Get-ConfigValue "EMBED_MODEL" "sentence-transformers/all-MiniLM-L6-v2"
    $embedDim = Get-ConfigValue "EMBED_DIM" "384"

    Invoke-Podman @(
        "run", "--rm", "--network", $network,
        "-e", "QDRANT_HOST=insurance-qdrant", "-e", "QDRANT_PORT=6333",
        "-e", "COLLECTION_NAME=$collection", "-e", "EMBED_DIM=$embedDim",
        $apiImage, "python", "src/app/rag/setup.py"
    )
    Invoke-Podman @(
        "run", "--rm", "--network", $network,
        "-e", "QDRANT_HOST=insurance-qdrant", "-e", "QDRANT_PORT=6333",
        "-e", "COLLECTION_NAME=$collection", "-e", "EMBED_MODEL=$embedModel",
        "-e", "EMBED_DIM=$embedDim", "-e", "EMBED_LOCAL_FILES_ONLY=false",
        "-v", "idle-chatbot-model-cache:/home/appuser/.cache/huggingface:U",
        $apiImage, "python", "scripts/ingest.py"
    )

    & podman container exists "insurance-api"
    if ($LASTEXITCODE -eq 0) { Invoke-Podman @("rm", "-f", "insurance-api") }

    $runArgs = @(
        "run", "-d", "--name", "insurance-api", "--network", $network,
        "--label", "io.idle-chatbot.stack=true",
        "-p", "$(Get-ConfigValue 'BIND_ADDRESS' '127.0.0.1'):$(Get-ConfigValue 'PORT' '8080'):8080"
    )
    if (Test-Path -LiteralPath $envFile) { $runArgs += @("--env-file", $envFile) }
    $runArgs += @(
        "-e", "HOST=0.0.0.0", "-e", "PORT=8080",
        "-e", "QDRANT_HOST=insurance-qdrant", "-e", "QDRANT_PORT=6333",
        "-e", "REDIS_URL=redis://insurance-redis:6379",
        "-e", "LLM_BASE_URL=http://insurance-ollama:11434/v1",
        "-e", "EMBED_LOCAL_FILES_ONLY=false",
        "-v", "idle-chatbot-model-cache:/home/appuser/.cache/huggingface:U"
    )
    $runArgs += @($apiImage)
    Invoke-Podman $runArgs
}

Ensure-PodmanMachine
Set-Location $root

switch ($Action) {
    "up"      { Start-CompleteStack }
    "infra"   { Start-Infrastructure }
    "down"    { Remove-StackContainers }
    "restart" {
        Remove-StackContainers
        Start-CompleteStack
    }
    "logs"    { Invoke-Podman @("logs", "-f", "insurance-api") }
    "status"  { Invoke-Podman @("ps", "-a", "--filter", "label=io.idle-chatbot.stack=true") }
}
