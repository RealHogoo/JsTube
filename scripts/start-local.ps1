param(
    [int]$BackendPort = 8084,
    [int]$FrontendPort = 5174,
    [int]$MongoPort = 27017,
    [switch]$ForceRestart,
    [switch]$InstallMongo
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$LogDir = Join-Path $Root "logs\local"
$NodeRuntime = Join-Path (Resolve-Path (Join-Path $Root "..")).Path "webhard-service\.runtime\node-v22.13.1"
$MongoRuntime = Join-Path $Root ".runtime\mongodb"
$BackendLog = Join-Path $LogDir "media-api.out.log"
$BackendErr = Join-Path $LogDir "media-api.err.log"
$FrontendLog = Join-Path $LogDir "media-front.out.log"
$FrontendErr = Join-Path $LogDir "media-front.err.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Step($Message) {
    Write-Host "[media-local] $Message"
}

function Get-PortProcessId([int]$Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) {
        return [int]$connection.OwningProcess
    }
    return $null
}

function Stop-PortProcess([int]$Port) {
    $pid = Get-PortProcessId $Port
    if ($pid) {
        Write-Step "Stopping process on port $Port (PID $pid)"
        Stop-Process -Id $pid -Force
        Start-Sleep -Seconds 1
    }
}

function Test-TcpPort([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-Http($Url, [int]$TimeoutSeconds = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $response
            }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    } while ((Get-Date) -lt $deadline)
    throw "HTTP check failed: $Url"
}

function Ensure-Mongo {
    if (Test-TcpPort $MongoPort) {
        Write-Step "MongoDB is listening on $MongoPort"
        return
    }

    $service = Get-Service | Where-Object {
        $_.Name -match "mongo|mongodb" -or $_.DisplayName -match "mongo|mongodb"
    } | Select-Object -First 1

    if ($service) {
        if ($service.Status -ne "Running") {
            Write-Step "Starting MongoDB service: $($service.Name)"
            Start-Service -Name $service.Name
        }
        $deadline = (Get-Date).AddSeconds(30)
        do {
            if (Test-TcpPort $MongoPort) {
                Write-Step "MongoDB started on $MongoPort"
                return
            }
            Start-Sleep -Seconds 1
        } while ((Get-Date) -lt $deadline)
        throw "MongoDB service started but port $MongoPort is not listening."
    }

    $mongod = Get-Command mongod -ErrorAction SilentlyContinue
    if (-not $mongod) {
        $runtimeMongod = Get-ChildItem -Path $MongoRuntime -Recurse -Filter mongod.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($runtimeMongod) {
            $mongod = @{ Source = $runtimeMongod.FullName }
        }
    }
    if ($mongod) {
        $MongoData = Join-Path $Root ".runtime\mongodb\data"
        $MongoLog = Join-Path $LogDir "mongod.log"
        New-Item -ItemType Directory -Force -Path $MongoData | Out-Null
        Write-Step "Starting mongod: $($mongod.Source)"
        Start-Process -FilePath $mongod.Source -ArgumentList "--dbpath `"$MongoData`" --bind_ip 127.0.0.1 --port $MongoPort --logpath `"$MongoLog`" --logappend" -WindowStyle Hidden
        $deadline = (Get-Date).AddSeconds(30)
        do {
            if (Test-TcpPort $MongoPort) {
                Write-Step "MongoDB started on $MongoPort"
                return
            }
            Start-Sleep -Seconds 1
        } while ((Get-Date) -lt $deadline)
        throw "mongod was started but port $MongoPort is not listening."
    }

    if (-not $InstallMongo) {
        throw "MongoDB is required but was not found. Re-run with -InstallMongo or install MongoDB Community Server."
    }

    Install-PortableMongo
    Ensure-Mongo
}

function Install-PortableMongo {
    $ArchiveUrl = "https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-8.0.15.zip"
    $ArchivePath = Join-Path $MongoRuntime "mongodb.zip"
    New-Item -ItemType Directory -Force -Path $MongoRuntime | Out-Null
    Write-Step "Downloading portable MongoDB: $ArchiveUrl"
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $ArchivePath -UseBasicParsing
    Write-Step "Extracting portable MongoDB"
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $MongoRuntime -Force
    $runtimeMongod = Get-ChildItem -Path $MongoRuntime -Recurse -Filter mongod.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $runtimeMongod) {
        throw "Portable MongoDB install failed: mongod.exe not found."
    }
    Write-Step "Portable MongoDB installed: $($runtimeMongod.FullName)"
}

function Ensure-Backend {
    if ($ForceRestart) {
        Stop-PortProcess $BackendPort
    }
    if (-not (Test-TcpPort $BackendPort)) {
        $python = Join-Path $BackendDir ".venv\Scripts\python.exe"
        if (-not (Test-Path $python)) {
            throw "Python venv not found: $python"
        }
        Write-Step "Starting media backend on $BackendPort"
        Start-Process -FilePath $python -ArgumentList "manage.py runserver 0.0.0.0:$BackendPort" -WorkingDirectory $BackendDir -RedirectStandardOutput $BackendLog -RedirectStandardError $BackendErr -WindowStyle Hidden
    } else {
        Write-Step "Media backend port $BackendPort is already listening"
    }

    $response = Wait-Http "http://127.0.0.1:$BackendPort/api/health/" 40
    $health = $response.Content | ConvertFrom-Json
    if ($health.data.mongo -ne "UP") {
        throw "Media backend is running but MongoDB health is $($health.data.mongo)."
    }
    Write-Step "Media backend is healthy"
}

function Ensure-Frontend {
    if ($ForceRestart) {
        Stop-PortProcess $FrontendPort
    }
    if (-not (Test-TcpPort $FrontendPort)) {
        $node = Join-Path $NodeRuntime "node.exe"
        if (-not (Test-Path $node)) {
            $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
            if (-not $nodeCommand) {
                throw "Node runtime not found."
            }
            $node = $nodeCommand.Source
        }
        Write-Step "Starting media frontend on $FrontendPort"
        Start-Process -FilePath $node -ArgumentList "node_modules/vite/bin/vite.js --host 0.0.0.0 --port $FrontendPort" -WorkingDirectory $FrontendDir -RedirectStandardOutput $FrontendLog -RedirectStandardError $FrontendErr -WindowStyle Hidden
    } else {
        Write-Step "Media frontend port $FrontendPort is already listening"
    }

    Wait-Http "http://127.0.0.1:$FrontendPort/?karaoke_tv=1" 30 | Out-Null
    Write-Step "Media frontend is healthy"
}

Ensure-Mongo
Ensure-Backend
Ensure-Frontend

Write-Host ""
Write-Host "Media service is ready:"
Write-Host "  API       http://localhost:$BackendPort"
Write-Host "  Frontend  http://localhost:$FrontendPort"
Write-Host "  TV        http://localhost:$FrontendPort/?karaoke_tv=1"
