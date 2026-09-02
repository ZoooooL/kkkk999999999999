# Run in PowerShell as Administrator on WALEEDX1 (Lenovo).
# Prepares D:\Zool Sulotion and OpenSSH so Odoo can SFTP to this PC.

$ErrorActionPreference = "Stop"
$path = "D:\Zool Sulotion"
New-Item -ItemType Directory -Force -Path $path | Out-Null

$cap = Get-WindowsCapability -Online | Where-Object Name -like "OpenSSH.Server*"
if ($cap -and $cap.State -ne "Installed") {
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
}

Start-Service sshd -ErrorAction SilentlyContinue
Set-Service -Name sshd -StartupType Automatic
New-NetFirewallRule -Name "sshd-brodan" -DisplayName "OpenSSH Server (sshd)" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -ErrorAction SilentlyContinue

Write-Host "SFTP Host = 192.168.8.18"
Write-Host "SFTP User = lenovo"
Write-Host "SFTP Path = D:/Zool Sulotion"
Write-Host "Share     = \\WALEEDX1\Zool Sulotion"
Write-Host "Type the Windows password for user lenovo in Odoo, then save."
Write-Host "If the Odoo server is on the internet, forward router port 22 to 192.168.8.18"
