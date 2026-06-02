param(
    [string]$Port = "COM4",
    [string]$Ssid = "NIWA-AP",
    [string]$ServerUrl = "http://10.42.0.1:5058"
)

$ErrorActionPreference = "Stop"
$securePassword = Read-Host "Password Wi-Fi per $Ssid" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$serial = $null

try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    $serial = [System.IO.Ports.SerialPort]::new($Port, 115200, "None", 8, "One")
    $serial.DtrEnable = $false
    $serial.RtsEnable = $false
    $serial.NewLine = "`n"
    $serial.ReadTimeout = 250
    $serial.Open()

    Start-Sleep -Milliseconds 650
    $serial.WriteLine("WIFI_SSID=$Ssid")
    $serial.WriteLine("WIFI_PASSWORD=$plainPassword")
    $serial.WriteLine("SERVER_URL=$ServerUrl")
    $serial.WriteLine("SAVE_WIFI")
    $serial.WriteLine("STATUS")
    Write-Host "Configurazione inviata a $Port. La password non viene salvata nel repository."

    $deadline = (Get-Date).AddSeconds(6)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 180
        $output = $serial.ReadExisting()
        if ($output) {
            Write-Host -NoNewline $output
        }
    }
} finally {
    $plainPassword = $null
    if ($serial -and $serial.IsOpen) {
        $serial.Close()
    }
    if ($serial) {
        $serial.Dispose()
    }
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
}
