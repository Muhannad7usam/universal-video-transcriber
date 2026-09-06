param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ruleName = "Universal Video Transcriber - Private LAN"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    throw "Open PowerShell as Administrator, then run this script again."
}

$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Remove-NetFirewallRule -DisplayName $ruleName
}

New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $Port `
    -Profile Private | Out-Null

Write-Host "Private-LAN firewall access enabled for TCP port $Port." -ForegroundColor Green
Write-Host "The rule applies only while Windows classifies the network as Private." -ForegroundColor DarkGray
