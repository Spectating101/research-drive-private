$ErrorActionPreference = "Stop"

$Results = [ordered]@{
  hostname = $env:COMPUTERNAME
  measured_at = (Get-Date).ToUniversalTime().ToString("o")
}

$DataCiteUrl = "https://api.datacite.org/dois?resource-types=dataset&page[size]=500&page[number]=1"
$Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$Response = Invoke-WebRequest -Uri $DataCiteUrl -UseBasicParsing -TimeoutSec 90
$Stopwatch.Stop()
$Results.datacite_seconds = [math]::Round($Stopwatch.Elapsed.TotalSeconds, 3)
$Results.datacite_bytes = $Response.RawContentLength
$Results.datacite_mbps = [math]::Round((($Response.RawContentLength * 8) / 1000000) / $Stopwatch.Elapsed.TotalSeconds, 3)

$DownloadUrl = "https://speed.cloudflare.com/__down?bytes=25000000"
$TempFile = Join-Path $env:TEMP "cluster_speed_test.bin"
$Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
Invoke-WebRequest -Uri $DownloadUrl -OutFile $TempFile -UseBasicParsing -TimeoutSec 120
$Stopwatch.Stop()
$Bytes = (Get-Item $TempFile).Length
$Results.download_seconds = [math]::Round($Stopwatch.Elapsed.TotalSeconds, 3)
$Results.download_bytes = $Bytes
$Results.download_mbps = [math]::Round((($Bytes * 8) / 1000000) / $Stopwatch.Elapsed.TotalSeconds, 3)
Remove-Item $TempFile -Force -ErrorAction SilentlyContinue

$Drive = Get-PSDrive C
$Results.disk_free_gb = [math]::Round($Drive.Free / 1GB, 2)
$Results.logical_processors = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
$Results.ram_gb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 2)

[PSCustomObject]$Results | ConvertTo-Json -Compress
