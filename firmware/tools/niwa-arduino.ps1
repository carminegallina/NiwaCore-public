param(
    [ValidateSet("info", "setup", "ports", "compile", "upload", "monitor")]
    [string]$Action = "info",
    [string]$Sketch = "",
    [string]$Port = "",
    [string]$Fqbn = "esp32:esp32:esp32cam"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ConfigDir = Join-Path $ProjectRoot ".arduino-cli"
$BuildRoot = Join-Path $ProjectRoot ".arduino-build"
$DefaultSketch = Join-Path $ProjectRoot "firmware\esp32cam-lights"
$Esp32Index = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"

$CliCandidates = @(
    (Join-Path $env:ProgramFiles "Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"),
    "arduino-cli.exe"
)

$ArduinoCli = $null
foreach ($Candidate in $CliCandidates) {
    if (Test-Path -LiteralPath $Candidate) {
        $ArduinoCli = $Candidate
        break
    }

    $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
    if ($Command) {
        $ArduinoCli = $Command.Source
        break
    }
}

if (-not $ArduinoCli) {
    throw "arduino-cli non trovato. Installa Arduino IDE oppure arduino-cli."
}

New-Item -ItemType Directory -Force -Path $ConfigDir, $BuildRoot | Out-Null

function Invoke-ArduinoCli {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    & $ArduinoCli --config-dir $ConfigDir @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "arduino-cli ha restituito il codice $LASTEXITCODE."
    }
}

function Resolve-SketchPath {
    if ($Sketch) {
        return (Resolve-Path $Sketch).Path
    }

    return $DefaultSketch
}

switch ($Action) {
    "info" {
        Invoke-ArduinoCli version
        Write-Host ""
        Write-Host "Config locale: $ConfigDir"
        Write-Host "Build locali: $BuildRoot"
        Write-Host "FQBN predefinito ESP32-CAM: $Fqbn"
    }
    "setup" {
        Invoke-ArduinoCli config init --overwrite
        Invoke-ArduinoCli config set board_manager.additional_urls $Esp32Index
        Invoke-ArduinoCli core update-index
        Invoke-ArduinoCli core install esp32:esp32
        Invoke-ArduinoCli core list
    }
    "ports" {
        Invoke-ArduinoCli board list
    }
    "compile" {
        $SketchPath = Resolve-SketchPath
        Invoke-ArduinoCli compile --fqbn $Fqbn --build-path $BuildRoot $SketchPath
    }
    "upload" {
        if (-not $Port) {
            throw "Specifica la porta seriale, ad esempio: -Port COM4"
        }

        $SketchPath = Resolve-SketchPath
        Invoke-ArduinoCli compile --fqbn $Fqbn --build-path $BuildRoot $SketchPath
        Invoke-ArduinoCli upload --fqbn $Fqbn --port $Port --build-path $BuildRoot $SketchPath
    }
    "monitor" {
        if (-not $Port) {
            throw "Specifica la porta seriale, ad esempio: -Port COM4"
        }

        Invoke-ArduinoCli monitor --port $Port --config baudrate=115200
    }
}
