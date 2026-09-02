# Run in PowerShell on WALEEDX1 (Lenovo). Opens Microsoft login, then prints a token.
# Paste the { ... } JSON into Odoo: Settings -> Backup -> OneDrive token.

$ErrorActionPreference = "Stop"
$dir = Join-Path $env:TEMP "brodan-rclone"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$zip = Join-Path $dir "rclone.zip"
$exe = Get-ChildItem -Path $dir -Recurse -Filter rclone.exe -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $exe) {
    Write-Host "Downloading rclone..."
    Invoke-WebRequest -Uri "https://downloads.rclone.org/rclone-current-windows-amd64.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $dir -Force
    $exe = Get-ChildItem -Path $dir -Recurse -Filter rclone.exe | Select-Object -First 1
}

Write-Host "A browser window will open. Sign in to the Microsoft account that has OneDrive space."
Write-Host "Free 5GB is not enough. Microsoft 365 (1TB) is required because the database is about 50GB."
Write-Host ""
& $exe.FullName authorize "onedrive"
Write-Host ""
Write-Host "Copy the JSON line that starts with { and ends with }"
Write-Host "Odoo -> Settings -> Backup -> paste into OneDrive token -> Save -> Backup now"
Write-Host "Folder = Brodansh_Backups"
Write-Host "Drive type = personal   (or business if this is Microsoft 365 work)"
