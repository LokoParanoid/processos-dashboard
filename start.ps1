param(
    [int]$Port = 8000,
    [switch]$NoBrowser,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

Write-Output "=== Processos Dashboard ==="
Write-Output ""

# Check Python
try {
    $pyVersion = python --version 2>&1
    if ($pyVersion -match "Python (\d+)\.(\d+)") {
        $major, $minor = [int]$Matches[1], [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
            Write-Output "ERRO: Python 3.10+ necessario. Instale em: https://www.python.org/downloads/"
            exit 1
        }
        Write-Output "Python: $pyVersion"
    }
} catch {
    Write-Output "ERRO: Python nao encontrado. Instale de: https://www.python.org/downloads/"
    pause; exit 1
}

# Create venv
$venvDir = Join-Path $ProjectDir ".venv"
if (-not (Test-Path -LiteralPath $venvDir)) {
    Write-Output "Criando ambiente virtual..."
    python -m venv $venvDir
    if (-not $?) { Write-Output "Falha ao criar venv"; pause; exit 1 }
}

# Activate venv
. "$venvDir\Scripts\Activate.ps1"

# Install dependencies
Write-Output "Verificando dependencias..."
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt
if (-not $?) { Write-Output "Falha ao instalar dependencias"; pause; exit 1 }

# Init DB (cria diretorio data/ e tabelas se necessario)
$dataDir = Join-Path $ProjectDir "data"
if (-not (Test-Path -LiteralPath $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir | Out-Null
}
python -c "from database import init_db; init_db()"
if (-not $?) { Write-Output "Falha ao criar banco de dados"; pause; exit 1 }

Write-Output ""
Write-Output "Iniciando servidor em http://localhost:$Port"
Write-Output "Pressione Ctrl+C para parar"
Write-Output ""

# Open browser
if (-not $NoBrowser) {
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:$Port"
}

# Start server
$uvicornArgs = @("main:app", "--host", "0.0.0.0", "--port", $Port)
if (-not $NoReload) { $uvicornArgs += "--reload" }

try {
    python -m uvicorn @uvicornArgs
} catch {
    Write-Output "Servidor encerrado."
}
