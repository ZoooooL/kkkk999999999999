#Requires -Version 5.1
<#
.SYNOPSIS
    ZoolBoost — تطبيق صيانة ويندوز بأسطورة الواجهة (WinForms / RTL).
.DESCRIPTION
    Legitimate Windows maintenance GUI only:
    - Safe TEMP / cache cleanup
    - Working-set trim via documented Windows APIs
    - Empty-file cleanup in user-chosen safe folders (Downloads / Temp)
    Never: malware, AV disable, process hiding, security-registry wipes, cheats.

    وضع التشغيل (أربع بطاقات في الأعلى):
      1) الوضع الانسيابي  — هدوء بصري، تنظيف لطيف، تنبيهات أقل
      2) وضع اللمس        — أهداف كبيرة ومسافات أوسع
      3) الوضع العادي     — متوازن (الافتراضي)
      4) وضع الجهاز       — تعزيز جهاز: RAM + ملفات فارغة + TEMP + كاش آمن

    Author / المستخدم: Waleed Mohamed (وليد محمد)
#>

# --- STA: WinForms يحتاج شقة أحادية الخيط ---
if ([System.Threading.Thread]::CurrentThread.GetApartmentState() -ne 'STA') {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = (Get-Process -Id $PID).Path
    $psi.Arguments = "-NoProfile -STA -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $psi.UseShellExecute = $true
    [void][System.Diagnostics.Process]::Start($psi)
    exit
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
[System.Windows.Forms.Application]::SetCompatibleTextRenderingDefault($false)

try {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class ZoolNative {
    [DllImport("psapi.dll")]
    public static extern int EmptyWorkingSet(IntPtr hProcess);
    [DllImport("user32.dll")]
    public static extern bool SetProcessDPIAware();
}
"@ -ErrorAction SilentlyContinue
    [void][ZoolNative]::SetProcessDPIAware()
} catch { }

# ===================== ألوان الأسطورة / Legendary palette =====================
$script:CBg       = [System.Drawing.Color]::FromArgb(12, 14, 22)
$script:CPanel    = [System.Drawing.Color]::FromArgb(22, 26, 40)
$script:CCard     = [System.Drawing.Color]::FromArgb(28, 34, 52)
$script:CGold     = [System.Drawing.Color]::FromArgb(232, 196, 92)
$script:CCyan     = [System.Drawing.Color]::FromArgb(70, 210, 230)
$script:CMuted    = [System.Drawing.Color]::FromArgb(150, 162, 190)
$script:CText     = [System.Drawing.Color]::FromArgb(242, 246, 255)
$script:CDanger   = [System.Drawing.Color]::FromArgb(230, 90, 90)
$script:COk       = [System.Drawing.Color]::FromArgb(90, 210, 140)
$script:CSmoothBg = [System.Drawing.Color]::FromArgb(16, 18, 24)

$script:Running   = $false
$script:Cancel    = $false
$script:Mode      = 'Normal'   # Smooth | Touch | Normal | Device
$script:LogQuiet  = $false

# مسارات محظورة — لا تُمس أبداً / never-touch system-critical roots
$script:BlockedRoots = @(
    "$env:SystemRoot",
    "$env:ProgramFiles",
    ${env:ProgramFiles(x86)},
    "$env:ProgramData",
    "$env:SystemDrive\Windows",
    "$env:SystemDrive\Program Files",
    "$env:SystemDrive\Boot",
    "$env:SystemDrive\Recovery",
    "$env:SystemDrive\PerfLogs"
) | Where-Object { $_ }

function Test-IsAdministrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Request-AdminElevation {
    $msg = @"
بعض عمليات تنظيف TEMP للنظام تحتاج صلاحيات المسؤول.

Some system TEMP cleanup needs Administrator rights.

هل تريد إعادة تشغيل ZoolBoost كمسؤول؟
Restart elevated?
"@
    $r = [System.Windows.Forms.MessageBox]::Show(
        $msg, 'ZoolBoost — صلاحيات',
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Shield)
    if ($r -ne [System.Windows.Forms.DialogResult]::Yes) { return $false }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = (Get-Process -Id $PID).Path
    $psi.Arguments = "-NoProfile -STA -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $psi.Verb = 'runas'
    $psi.UseShellExecute = $true
    try {
        [void][System.Diagnostics.Process]::Start($psi)
        return $true
    } catch {
        [System.Windows.Forms.MessageBox]::Show(
            "لم يتم منح صلاحيات المسؤول.`nElevation cancelled.",
            'ZoolBoost', [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
        return $false
    }
}

function Get-SafeTempRoots {
    @(
        [IO.Path]::GetTempPath(),
        $env:TEMP,
        $env:TMP,
        "$env:LOCALAPPDATA\Temp"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
}

function Get-SafeBrowserCacheDirs {
    $dirs = New-Object System.Collections.Generic.List[string]
    $candidates = @(
        "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache",
        "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Code Cache",
        "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\GPUCache",
        "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Cache",
        "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Code Cache",
        "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\GPUCache",
        "$env:LOCALAPPDATA\Microsoft\Windows\INetCache",
        "$env:LOCALAPPDATA\Mozilla\Firefox\Profiles"
    )
    foreach ($c in $candidates) {
        if (-not (Test-Path -LiteralPath $c)) { continue }
        if ($c -like '*\Firefox\Profiles') {
            Get-ChildItem -LiteralPath $c -Directory -ErrorAction SilentlyContinue |
                ForEach-Object {
                    $cache2 = Join-Path $_.FullName 'cache2'
                    if (Test-Path $cache2) { [void]$dirs.Add($cache2) }
                }
        } else {
            [void]$dirs.Add($c)
        }
    }
    return $dirs
}

function Test-PathIsBlocked {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $true }
    try {
        $full = [IO.Path]::GetFullPath($Path)
    } catch { return $true }

    foreach ($b in $script:BlockedRoots) {
        if ([string]::IsNullOrWhiteSpace($b)) { continue }
        try {
            $br = [IO.Path]::GetFullPath($b).TrimEnd('\')
            if ($full.StartsWith($br + '\', [StringComparison]::OrdinalIgnoreCase) -or
                $full.Equals($br, [StringComparison]::OrdinalIgnoreCase)) {
                # TEMP داخل Windows مسموح فقط لمجلد Temp نفسه
                $winTemp = Join-Path $env:SystemRoot 'Temp'
                if ($full.StartsWith([IO.Path]::GetFullPath($winTemp), [StringComparison]::OrdinalIgnoreCase)) {
                    return $false
                }
                return $true
            }
        } catch { }
    }
    return $false
}

function Test-PathIsSafeEmptyTarget {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    if (Test-PathIsBlocked $Path) { return $false }
    try { $full = [IO.Path]::GetFullPath($Path) } catch { return $false }

    $downloads = [Environment]::GetFolderPath('UserProfile')
    if ($downloads) { $downloads = Join-Path $downloads 'Downloads' }
    $allowed = @()
    if ($downloads) { $allowed += $downloads }
    $allowed += @(Get-SafeTempRoots)
    $allowed += [Environment]::GetFolderPath('InternetCache')

    foreach ($a in $allowed) {
        if (-not $a) { continue }
        try {
            $ar = [IO.Path]::GetFullPath($a).TrimEnd('\')
            if ($full.StartsWith($ar + '\', [StringComparison]::OrdinalIgnoreCase) -or
                $full.Equals($ar, [StringComparison]::OrdinalIgnoreCase)) {
                return $true
            }
        } catch { }
    }
    return $false
}

function Write-BoostLog {
    param([string]$Text, [string]$Level = 'info')
    if ($script:LogQuiet -and $Level -eq 'debug') { return }
    $ts = Get-Date -Format 'HH:mm:ss'
    $line = "[$ts] $Text"
    if ($script:LogBox -and -not $script:LogBox.IsDisposed) {
        $script:LogBox.AppendText($line + [Environment]::NewLine)
        $script:LogBox.SelectionStart = $script:LogBox.Text.Length
        $script:LogBox.ScrollToCaret()
        [System.Windows.Forms.Application]::DoEvents()
    }
}

function Set-ProgressSafe {
    param([int]$Value)
    if ($script:Bar -and -not $script:Bar.IsDisposed) {
        $v = [Math]::Max(0, [Math]::Min(100, $Value))
        $script:Bar.Value = $v
        [System.Windows.Forms.Application]::DoEvents()
    }
}

function Confirm-Destructive {
    param([string]$Detail)
    if ($script:Mode -eq 'Smooth') {
        # fewer prompts: one bundled confirm already done at Start
        return $true
    }
    $r = [System.Windows.Forms.MessageBox]::Show(
        "$Detail`n`nهذا حذف لملفات مؤقتة/كاش/فارغة فقط — لا يمس ملفات النظام الحساسة.`nSafe temp/cache/empty cleanup only.`n`nمتابعة؟",
        'تأكيد السلامة — ZoolBoost',
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Warning)
    return ($r -eq [System.Windows.Forms.DialogResult]::Yes)
}

function Clear-DirectoryContentsSafe {
    param(
        [string]$Dir,
        [switch]$Gentle
    )
    if (-not (Test-Path -LiteralPath $Dir)) { return 0 }
    if (Test-PathIsBlocked $Dir -and $Dir -notmatch '\\Temp$') { return 0 }

    $removed = 0
    $opt = @{ LiteralPath = $Dir; Force = $true; ErrorAction = 'SilentlyContinue' }
    $items = @(Get-ChildItem @opt)
    if ($Gentle) {
        # انسيابي: أقدم من يوم واحد فقط / older than 1 day
        $cut = (Get-Date).AddDays(-1)
        $items = $items | Where-Object { $_.LastWriteTime -lt $cut }
    }
    foreach ($it in $items) {
        if ($script:Cancel) { break }
        [System.Windows.Forms.Application]::DoEvents()
        try {
            if ($it.PSIsContainer) {
                Remove-Item -LiteralPath $it.FullName -Recurse -Force -ErrorAction Stop
            } else {
                Remove-Item -LiteralPath $it.FullName -Force -ErrorAction Stop
            }
            $removed++
        } catch {
            Write-BoostLog "تخطي (مفتوح/محمي): $($it.Name)" 'debug'
        }
    }
    return $removed
}

function Remove-EmptyFilesAndFolders {
    param([string]$Root)
    if (-not (Test-PathIsSafeEmptyTarget $Root)) {
        Write-BoostLog "رفض المسار غير الآمن: $Root" 'warn'
        return 0
    }
    $n = 0
    Get-ChildItem -LiteralPath $Root -Recurse -Force -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -eq 0 } |
        ForEach-Object {
            if ($script:Cancel) { return }
            [System.Windows.Forms.Application]::DoEvents()
            try {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop
                $n++
            } catch { }
        }
    Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory -ErrorAction SilentlyContinue |
        Sort-Object { $_.FullName.Length } -Descending |
        ForEach-Object {
            if ($script:Cancel) { return }
            try {
                if (-not (Get-ChildItem -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue)) {
                    Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop
                    $n++
                }
            } catch { }
        }
    return $n
}

function Invoke-RamTrim {
    # توثيق Microsoft: EmptyWorkingSet يقلّص مجموعة العمل للعملية الحالية
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
    [GC]::Collect()
    $trimmed = 0
    try {
        $procs = Get-Process -ErrorAction SilentlyContinue |
            Where-Object { $_.Id -eq $PID -or $_.ProcessName -in @('explorer') }
        foreach ($p in $procs) {
            try {
                [void][ZoolNative]::EmptyWorkingSet($p.Handle)
                $trimmed++
            } catch { }
        }
        # اقتراح إغاثة للذاكرة عبر تقليص مجموعة عمل العمليات الخاصة بالمستخدم فقط
        $me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $meShort = $me.Split('\')[-1]
        Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
            if ($script:Cancel) { return }
            [System.Windows.Forms.Application]::DoEvents()
            try {
                $po = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue
                if (-not $po) { return }
                $owner = $po | Invoke-CimMethod -MethodName GetOwner -ErrorAction SilentlyContinue
                if ($owner -and $owner.User -and ($owner.User -eq $meShort)) {
                    [void][ZoolNative]::EmptyWorkingSet($_.Handle)
                    $trimmed++
                }
            } catch { }
        }
    } catch {
        Write-BoostLog "RAM trim جزئي: $($_.Exception.Message)"
    }
    return $trimmed
}

function Start-MaintenanceJob {
    $gentle = ($script:Mode -eq 'Smooth')
    $device = ($script:Mode -eq 'Device')

    Write-BoostLog "▶ بدء الوضع: $($script:ModeLabel.Text)"
    Set-ProgressSafe 5

    $totalRemoved = 0
    $temps = @(Get-SafeTempRoots)
    if ((Test-IsAdministrator)) {
        $winTemp = Join-Path $env:SystemRoot 'Temp'
        if (Test-Path $winTemp) { $temps += $winTemp }
    }

    $i = 0
    foreach ($t in ($temps | Select-Object -Unique)) {
        if ($script:Cancel) { break }
        $i++
        Write-BoostLog "تنظيف TEMP: $t"
        $totalRemoved += [int](Clear-DirectoryContentsSafe -Dir $t -Gentle:$gentle)
        Set-ProgressSafe (10 + [int](20 * $i / [Math]::Max(1, $temps.Count)))
    }

    if ($script:Cancel) { Write-BoostLog "■ أوقف المستخدم العملية"; return }

    if (-not $gentle -or $device) {
        if (-not $script:SkipCacheConfirm) {
            if (-not (Confirm-Destructive "مسح كاش المتصفح/النظام الآمن؟`nClear safe browser/system caches?")) {
                Write-BoostLog "تم تخطي الكاش بناءً على اختيارك."
            } else {
                $script:SkipCacheConfirm = $true
                $caches = @(Get-SafeBrowserCacheDirs)
                $ci = 0
                foreach ($c in $caches) {
                    if ($script:Cancel) { break }
                    $ci++
                    Write-BoostLog "كاش آمن: $c"
                    $totalRemoved += [int](Clear-DirectoryContentsSafe -Dir $c -Gentle:$gentle)
                    Set-ProgressSafe (35 + [int](25 * $ci / [Math]::Max(1, $caches.Count)))
                }
            }
        }
    } else {
        Write-BoostLog "الوضع الانسيابي: كاش خفيف فقط (TEMP الأقدم من يوم)."
    }

    Set-ProgressSafe 70
    if ($script:Cancel) { Write-BoostLog "■ أوقف المستخدم العملية"; return }

    if ($device -or $script:EmptyTarget) {
        $target = $script:EmptyTarget
        if (-not $target) {
            $dl = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Downloads'
            $target = $dl
        }
        if (Test-PathIsSafeEmptyTarget $target) {
            if ($gentle -or (Confirm-Destructive "حذف الملفات/المجلدات الفارغة في:`n$target")) {
                Write-BoostLog "ملفات فارغة في: $target"
                $n = Remove-EmptyFilesAndFolders -Root $target
                $totalRemoved += $n
                Write-BoostLog "حُذف فارغ: $n"
            }
        } else {
            Write-BoostLog "مسار الملفات الفارغة غير مسموح (Downloads/Temp فقط)."
        }
    }

    Set-ProgressSafe 85
    if ($script:Cancel) { Write-BoostLog "■ أوقف المستخدم العملية"; return }

    if ($device -or -not $gentle) {
        Write-BoostLog "تقليص مجموعة العمل (RAM) عبر EmptyWorkingSet..."
        $tn = Invoke-RamTrim
        Write-BoostLog "عمليات تم تقليص مجموعتها: $tn"
    } else {
        [GC]::Collect()
        Write-BoostLog "انسيابي: تجميع GC فقط بدون تقليص واسع."
    }

    Set-ProgressSafe 100
    Write-BoostLog "✓ اكتمل. عناصر أُزيلت تقريباً: $totalRemoved"
}

# ===================== UI =====================
$script:Form = New-Object System.Windows.Forms.Form
$script:Form.Text = 'ZoolBoost — وليد محمد'
$script:Form.StartPosition = 'CenterScreen'
$script:Form.BackColor = $script:CBg
$script:Form.ForeColor = $script:CText
$script:Form.Font = New-Object System.Drawing.Font('Segoe UI', 11)
$script:Form.Size = New-Object System.Drawing.Size(1100, 760)
$script:Form.MinimumSize = New-Object System.Drawing.Size(960, 680)
$script:Form.RightToLeft = [System.Windows.Forms.RightToLeft]::Yes
$script:Form.RightToLeftLayout = $true
$script:Form.KeyPreview = $true

function New-RoundPanel {
    param($X,$Y,$W,$H,$Back)
    $p = New-Object System.Windows.Forms.Panel
    $p.Location = New-Object System.Drawing.Point($X,$Y)
    $p.Size = New-Object System.Drawing.Size($W,$H)
    $p.BackColor = $Back
    return $p
}

# عنوان
$header = New-RoundPanel 16 12 1050 78 $script:CPanel
$header.Anchor = 'Top,Left,Right'
$script:Form.Controls.Add($header)

$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Text = 'ZoolBoost  ◆  تعزيز أسطوري'
$lblTitle.Font = New-Object System.Drawing.Font('Segoe UI Semibold', 22)
$lblTitle.ForeColor = $script:CGold
$lblTitle.AutoSize = $true
$lblTitle.Location = New-Object System.Drawing.Point(20, 10)
$header.Controls.Add($lblTitle)

$lblSub = New-Object System.Windows.Forms.Label
$lblSub.Text = 'وليد محمد  ·  صيانة شرعية فقط  ·  TEMP · كاش آمن · RAM · ملفات فارغة'
$lblSub.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$lblSub.ForeColor = $script:CCyan
$lblSub.AutoSize = $true
$lblSub.Location = New-Object System.Drawing.Point(22, 48)
$header.Controls.Add($lblSub)

$script:AdminBadge = New-Object System.Windows.Forms.Label
$script:AdminBadge.AutoSize = $true
$script:AdminBadge.Font = New-Object System.Drawing.Font('Segoe UI', 9)
$script:AdminBadge.Location = New-Object System.Drawing.Point(780, 18)
if (Test-IsAdministrator) {
    $script:AdminBadge.Text = 'صلاحيات: مسؤول'
    $script:AdminBadge.ForeColor = $script:COk
} else {
    $script:AdminBadge.Text = 'صلاحيات: مستخدم'
    $script:AdminBadge.ForeColor = $script:CMuted
}
$header.Controls.Add($script:AdminBadge)

# بطاقات الأوضاع في الأعلى — Mode cards at TOP
$modesHost = New-Object System.Windows.Forms.FlowLayoutPanel
$modesHost.Location = New-Object System.Drawing.Point(16, 100)
$modesHost.Size = New-Object System.Drawing.Size(1050, 168)
$modesHost.Anchor = 'Top,Left,Right'
$modesHost.BackColor = $script:CBg
$modesHost.FlowDirection = [System.Windows.Forms.FlowDirection]::RightToLeft
$modesHost.WrapContents = $false
$modesHost.Padding = New-Object System.Windows.Forms.Padding(0)
$script:Form.Controls.Add($modesHost)

$script:ModeCards = @{}

function Add-ModeCard {
    param(
        [string]$Key,
        [string]$Title,
        [string]$Hint
    )
    $card = New-Object System.Windows.Forms.Panel
    $card.Size = New-Object System.Drawing.Size(248, 152)
    $card.Margin = New-Object System.Windows.Forms.Padding(8, 4, 8, 4)
    $card.BackColor = $script:CCard
    $card.Cursor = [System.Windows.Forms.Cursors]::Hand
    $card.Tag = $Key

    $t = New-Object System.Windows.Forms.Label
    $t.Text = $Title
    $t.Font = New-Object System.Drawing.Font('Segoe UI Semibold', 13)
    $t.ForeColor = $script:CGold
    $t.AutoSize = $false
    $t.Size = New-Object System.Drawing.Size(228, 40)
    $t.Location = New-Object System.Drawing.Point(10, 12)
    $t.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
    $card.Controls.Add($t)

    $h = New-Object System.Windows.Forms.Label
    $h.Text = $Hint
    $h.Font = New-Object System.Drawing.Font('Segoe UI', 9)
    $h.ForeColor = $script:CMuted
    $h.AutoSize = $false
    $h.Size = New-Object System.Drawing.Size(228, 86)
    $h.Location = New-Object System.Drawing.Point(10, 54)
    $h.TextAlign = [System.Drawing.ContentAlignment]::TopCenter
    $card.Controls.Add($h)

    $card.Add_Click({ Select-BoostMode -Key $this.Tag })
    $t.Add_Click({ Select-BoostMode -Key $this.Parent.Tag })
    $h.Add_Click({ Select-BoostMode -Key $this.Parent.Tag })

    [void]$modesHost.Controls.Add($card)
    $script:ModeCards[$Key] = $card
}

Add-ModeCard 'Smooth' 'الوضع الانسيابي' "هدوء بصري · تنظيف لطيف`nتنبيهات أقل · ضوضاء أقل"
Add-ModeCard 'Touch'  'وضع اللمس'       "أزرار كبيرة · مسافات أوسع`nمريح للمس والشاشات"
Add-ModeCard 'Normal' 'الوضع العادي'    "متوازن · الافتراضي`nتنظيف آمن مع تأكيد"
Add-ModeCard 'Device' 'وضع الجهاز'      "تعزيز RAM · ملفات فارغة`nTEMP + كاش آمن"

$script:ModeLabel = New-Object System.Windows.Forms.Label
$script:ModeLabel.Text = 'الوضع العادي'
$script:ModeLabel.Visible = $false
$script:Form.Controls.Add($script:ModeLabel)

function Apply-TouchLayout {
    param([bool]$Touch)
    $base = if ($Touch) { 14 } else { 11 }
    $script:Form.Font = New-Object System.Drawing.Font('Segoe UI', $base)
    foreach ($b in @($script:BtnStart, $script:BtnStop, $script:BtnAdmin, $script:BtnFolder, $script:BtnDesktop)) {
        if (-not $b) { continue }
        $b.Height = if ($Touch) { 56 } else { 44 }
        $b.Font = New-Object System.Drawing.Font('Segoe UI Semibold', $(if ($Touch) { 13 } else { 11 }))
    }
    if ($script:LogBox) {
        $script:LogBox.Font = New-Object System.Drawing.Font('Consolas', $(if ($Touch) { 11 } else { 9 }))
    }
    $modesHost.Height = if ($Touch) { 188 } else { 168 }
    foreach ($c in $script:ModeCards.Values) {
        $c.Height = if ($Touch) { 172 } else { 152 }
        $c.Width  = if ($Touch) { 258 } else { 248 }
        $c.Margin = if ($Touch) {
            New-Object System.Windows.Forms.Padding(12, 6, 12, 6)
        } else {
            New-Object System.Windows.Forms.Padding(8, 4, 8, 4)
        }
    }
}

function Select-BoostMode {
    param([string]$Key)
    $script:Mode = $Key
    $script:LogQuiet = ($Key -eq 'Smooth')
    $names = @{
        Smooth = 'الوضع الانسيابي'
        Touch  = 'وضع اللمس'
        Normal = 'الوضع العادي'
        Device = 'وضع الجهاز'
    }
    $script:ModeLabel.Text = $names[$Key]
    foreach ($k in $script:ModeCards.Keys) {
        $card = $script:ModeCards[$k]
        if ($k -eq $Key) {
            $card.BackColor = [System.Drawing.Color]::FromArgb(48, 42, 22)
            $card.Padding = New-Object System.Windows.Forms.Padding(3)
        } else {
            $card.BackColor = if ($Key -eq 'Smooth') { $script:CSmoothBg } else { $script:CCard }
        }
    }
    if ($Key -eq 'Smooth') {
        $script:Form.BackColor = $script:CSmoothBg
        $modesHost.BackColor = $script:CSmoothBg
    } else {
        $script:Form.BackColor = $script:CBg
        $modesHost.BackColor = $script:CBg
    }
    Apply-TouchLayout -Touch:($Key -eq 'Touch')
    Write-BoostLog "تم اختيار: $($names[$Key])"
}

# لوحة التحكم
$ctrl = New-RoundPanel 16 278 1050 90 $script:CPanel
$ctrl.Anchor = 'Top,Left,Right'
$script:Form.Controls.Add($ctrl)

function New-GoldButton {
    param($Text, $X, $W, [System.Drawing.Color]$Fore)
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $Text
    $b.Location = New-Object System.Drawing.Point($X, 22)
    $b.Size = New-Object System.Drawing.Size($W, 44)
    $b.FlatStyle = 'Flat'
    $b.FlatAppearance.BorderColor = $script:CGold
    $b.FlatAppearance.BorderSize = 1
    $b.BackColor = [System.Drawing.Color]::FromArgb(36, 32, 18)
    $b.ForeColor = $Fore
    $b.Cursor = [System.Windows.Forms.Cursors]::Hand
    return $b
}

$script:BtnStart = New-GoldButton '▶  تشغيل' 20 160 $script:CGold
$script:BtnStop  = New-GoldButton '■  إيقاف' 190 140 $script:CDanger
$script:BtnStop.Enabled = $false
$script:BtnAdmin = New-GoldButton 'درع المسؤول' 340 160 $script:CCyan
$script:BtnFolder = New-GoldButton 'مجلد فارغ…' 510 160 $script:CText
$script:BtnDesktop = New-GoldButton 'نسخ لسطح المكتب' 680 200 $script:CCyan

$ctrl.Controls.AddRange(@(
    $script:BtnStart, $script:BtnStop, $script:BtnAdmin,
    $script:BtnFolder, $script:BtnDesktop
))

$script:PathHint = New-Object System.Windows.Forms.Label
$script:PathHint.Text = 'هدف الملفات الفارغة: Downloads (آمن)'
$script:PathHint.ForeColor = $script:CMuted
$script:PathHint.AutoSize = $true
$script:PathHint.Location = New-Object System.Drawing.Point(20, 68)
$ctrl.Controls.Add($script:PathHint)

$script:Bar = New-Object System.Windows.Forms.ProgressBar
$script:Bar.Location = New-Object System.Drawing.Point(16, 378)
$script:Bar.Size = New-Object System.Drawing.Size(1050, 18)
$script:Bar.Anchor = 'Top,Left,Right'
$script:Bar.Style = 'Continuous'
$script:Form.Controls.Add($script:Bar)

$script:LogBox = New-Object System.Windows.Forms.RichTextBox
$script:LogBox.Location = New-Object System.Drawing.Point(16, 406)
$script:LogBox.Size = New-Object System.Drawing.Size(1050, 300)
$script:LogBox.Anchor = 'Top,Bottom,Left,Right'
$script:LogBox.BackColor = [System.Drawing.Color]::FromArgb(10, 12, 18)
$script:LogBox.ForeColor = $script:CCyan
$script:LogBox.BorderStyle = 'None'
$script:LogBox.ReadOnly = $true
$script:LogBox.Font = New-Object System.Drawing.Font('Consolas', 9)
$script:LogBox.RightToLeft = [System.Windows.Forms.RightToLeft]::Yes
$script:Form.Controls.Add($script:LogBox)

$script:BtnStart.Add_Click({
    if ($script:Running) { return }

    $needAdmin = -not (Test-IsAdministrator)
    if ($script:Mode -eq 'Device' -and $needAdmin) {
        $ask = [System.Windows.Forms.MessageBox]::Show(
            "وضع الجهاز يستفيد من TEMP النظام. طلب صلاحيات المسؤول الآن؟`nDevice mode can use Windows\\Temp with elevation.",
            'ZoolBoost',
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Shield)
        if ($ask -eq [System.Windows.Forms.DialogResult]::Yes) {
            if (Request-AdminElevation) { $script:Form.Close(); return }
        }
    }

    $bundle = if ($script:Mode -eq 'Smooth') {
        "الوضع الانسيابي: تنظيف لطيف لـ TEMP (أقدم من يوم) بدون ضوضاء.`nهل نبدأ؟"
    } else {
        "سيتم تنظيف مجلدات TEMP وكاش آمن (اختياري) وقد تُحذف ملفات فارغة في Downloads/Temp فقط.`nلن تُمس مسارات النظام الحساسة.`n`nبدء ZoolBoost؟"
    }
    $ok = [System.Windows.Forms.MessageBox]::Show(
        $bundle, 'تأكيد السلامة — ZoolBoost',
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question)
    if ($ok -ne [System.Windows.Forms.DialogResult]::Yes) { return }

    $script:Running = $true
    $script:Cancel = $false
    $script:SkipCacheConfirm = ($script:Mode -eq 'Smooth')
    $script:BtnStart.Enabled = $false
    $script:BtnStop.Enabled = $true
    Set-ProgressSafe 0

    # صيانة على خيط الواجهة مع DoEvents حتى يبقى الإيقاف متاحاً
    try {
        Start-MaintenanceJob
    } catch {
        Write-BoostLog "خطأ: $($_.Exception.Message)"
    } finally {
        $script:Running = $false
        $script:BtnStart.Enabled = $true
        $script:BtnStop.Enabled = $false
    }
})

$script:BtnStop.Add_Click({
    $script:Cancel = $true
    Write-BoostLog "طلب إيقاف…"
})

$script:BtnAdmin.Add_Click({
    if (Test-IsAdministrator) {
        [System.Windows.Forms.MessageBox]::Show('التطبيق يعمل أصلاً كمسؤول.', 'ZoolBoost') | Out-Null
        return
    }
    if (Request-AdminElevation) { $script:Form.Close() }
})

$script:BtnFolder.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = 'اختر Downloads أو Temp فقط — مجلدات آمنة للملفات الفارغة'
    $dlg.SelectedPath = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Downloads'
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        if (Test-PathIsSafeEmptyTarget $dlg.SelectedPath) {
            $script:EmptyTarget = $dlg.SelectedPath
            $script:PathHint.Text = "هدف الملفات الفارغة: $($dlg.SelectedPath)"
            Write-BoostLog "مجلد آمن محدد: $($dlg.SelectedPath)"
        } else {
            [System.Windows.Forms.MessageBox]::Show(
                "المسار مرفوض. المسموح: مجلد التنزيلات أو TEMP فقط.`nBlocked: not Downloads/Temp.",
                'ZoolBoost — حماية',
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Stop) | Out-Null
        }
    }
})

$script:BtnDesktop.Add_Click({
    try {
        $desk = [Environment]::GetFolderPath('Desktop')
        $dest = Join-Path $desk 'ZoolBoost.ps1'
        Copy-Item -LiteralPath $PSCommandPath -Destination $dest -Force
        Write-BoostLog "نُسخ إلى سطح المكتب: $dest"
        [System.Windows.Forms.MessageBox]::Show(
            "تم النسخ إلى:`n$dest`n`nتشغيل:`npowershell -ExecutionPolicy Bypass -File `"$dest`"",
            'ZoolBoost') | Out-Null
    } catch {
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'ZoolBoost') | Out-Null
    }
})

$script:Form.Add_Shown({
    Select-BoostMode -Key 'Normal'
    Write-BoostLog 'مرحباً وليد محمد — ZoolBoost جاهز. صيانة شرعية فقط.'
    Write-BoostLog 'Unblock: powershell -ExecutionPolicy Bypass -File ZoolBoost.ps1'
})

$script:Form.Add_FormClosing({
    $script:Cancel = $true
})

[void][System.Windows.Forms.Application]::Run($script:Form)
