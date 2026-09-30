param(
    [string]$Port = "COM4",
    [string]$Ssid = "NIWA-AP",
    [string]$ServerUrl = "http://10.42.0.1:5057/api/bridge/v1",
    [string]$PiHost = "192.168.1.101",
    [string]$PiUser = "niwa",
    [string]$IdentityFile = "",
    [string]$SshExe = "ssh",
    [switch]$SkipToken
)

$ErrorActionPreference = "Stop"

function Get-BridgeToken {
    $sshArgs = @()
    if ($IdentityFile) { $sshArgs += @("-i", $IdentityFile) }
    $sshArgs += @("-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "$PiUser@$PiHost")
    $sshArgs += "curl -s -m 5 http://127.0.0.1:5057/api/bridge/v1/provision/token"

    Write-Host "Lettura del bridge token da $PiUser@$PiHost (solo loopback sul Raspberry)..."
    $raw = & $SshExe @sshArgs
    if ($LASTEXITCODE -ne 0 -or -not $raw) {
        throw ("Impossibile leggere il bridge token dal Raspberry. " +
               "Prova un altro client con -SshExe 'C:\Program Files\Git\usr\bin\ssh.exe', " +
               "oppure usa -SkipToken per lasciare il token gia' salvato sulla scheda.")
    }
    $parsed = $raw | ConvertFrom-Json
    if (-not $parsed.token) {
        throw "Risposta del provisioning token non valida."
    }
    return $parsed.token
}

$token = $null
if (-not $SkipToken) {
    $token = Get-BridgeToken
    Write-Host ("Bridge token letto: {0} caratteri." -f $token.Length)
}

$securePassword = Read-Host "Password Wi-Fi per $Ssid" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$serial = $null

try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    if (-not $plainPassword) {
        throw "Password vuota: l'hotspot NIWA-AP e' protetto WPA2."
    }
    if ($plainPassword.Length -lt 8 -or $plainPassword.Length -gt 63) {
        throw ("Password di {0} caratteri: una PSK WPA2 deve essere fra 8 e 63. " +
               "Nulla e' stato inviato alla scheda." -f $plainPassword.Length)
    }
    if ($plainPassword -ne $plainPassword.Trim()) {
        Write-Warning ("La password ha spazi iniziali o finali: il firmware li rimuove " +
                       "con trim() sulla riga seriale.")
    }
    Write-Host ("Password inserita: {0} caratteri. Confrontala con la riga STATUS qui sotto." -f $plainPassword.Length)

    try {
        $serial = [System.IO.Ports.SerialPort]::new($Port, 115200, "None", 8, "One")
        $serial.DtrEnable = $false
        $serial.RtsEnable = $false
        $serial.NewLine = "`n"
        $serial.ReadTimeout = 250
        $serial.Open()
    } catch {
        throw "Impossibile aprire $Port. Chiudi il Monitor Seriale dell'Arduino IDE e riprova. ($($_.Exception.Message))"
    }

    Start-Sleep -Milliseconds 2500
    $serial.DiscardInBuffer()

    $serial.WriteLine("WIFI_SSID=$Ssid")
    Start-Sleep -Milliseconds 150
    $serial.WriteLine("WIFI_PASSWORD=$plainPassword")
    Start-Sleep -Milliseconds 150
    $serial.WriteLine("SERVER_URL=$ServerUrl")
    Start-Sleep -Milliseconds 150
    if ($token) {
        $serial.WriteLine("BRIDGE_TOKEN=$token")
        Start-Sleep -Milliseconds 150
    }
    $serial.WriteLine("SAVE_CONFIG")
    Start-Sleep -Milliseconds 1500
    # Senza camera collegata il bridge non si connette da solo: forziamo un
    # tentativo per verificare subito la PSK.
    $serial.WriteLine("WIFI_CONNECT")
    Write-Host "Configurazione inviata a $Port. Nessun segreto viene scritto su disco o nel repository."

    # STATUS viene chiesto dopo ~28 s, il tempo di completare l'handshake Wi-Fi.
    $start = Get-Date
    $statusAt = $start.AddSeconds(28)
    $deadline = $start.AddSeconds(40)
    $statusSent = $false
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 200
        $output = $serial.ReadExisting()
        if ($output) {
            Write-Host -NoNewline $output
        }
        if (-not $statusSent -and (Get-Date) -gt $statusAt) {
            $serial.WriteLine("STATUS")
            $statusSent = $true
        }
    }
} finally {
    $plainPassword = $null
    $token = $null
    if ($serial -and $serial.IsOpen) { $serial.Close() }
    if ($serial) { $serial.Dispose() }
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
}
