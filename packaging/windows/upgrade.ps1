<#
xgame 自动升级：把更新的安装包换到当前这份上，数据目录原地不动。

由「升级.bat」**复制到 %TEMP% 之后**再执行——升级最后要把整个 xgame 目录改名，而正在被
PowerShell 读取的脚本文件就在那个目录里，Windows 不允许改名含已打开文件的目录。所以脚本
必须跑到包外面去，包在哪由 -Root 传进来。

流程：找更新的包 → 让服务优雅退出 → 解压到旁边的暂存目录 → 把数据和配置搬进去 →
整个目录改名交换 → 重新启动。
#>
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [switch]$Auto
)

$ErrorActionPreference = 'Stop'

function Write-Step([string]$Message) {
    Write-Host $Message
}

# 版本号按数字段比大小（v1.10.0 > v1.9.0），不按字符串比
function Compare-Version([string]$Left, [string]$Right) {
    $a = @([regex]::Matches($Left, '\d+') | ForEach-Object { [int]$_.Value })
    $b = @([regex]::Matches($Right, '\d+') | ForEach-Object { [int]$_.Value })
    $length = [Math]::Max($a.Count, $b.Count)
    for ($i = 0; $i -lt $length; $i++) {
        $x = if ($i -lt $a.Count) { $a[$i] } else { 0 }
        $y = if ($i -lt $b.Count) { $b[$i] } else { 0 }
        if ($x -gt $y) { return 1 }
        if ($x -lt $y) { return -1 }
    }
    return 0
}

function Test-PortOpen([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect('127.0.0.1', $Port)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

# 读 xgame.ini 里的 data_dir（跳过注释行）；没配就按默认的 <包目录>\data
function Get-ConfiguredDataDir([string]$PackageRoot) {
    $fallback = Join-Path $PackageRoot 'data'
    $ini = Join-Path $PackageRoot 'xgame.ini'
    if (-not (Test-Path $ini)) { return $fallback }
    $line = Get-Content -LiteralPath $ini -Encoding UTF8 |
        Where-Object { $_ -notmatch '^\s*[#;]' -and $_ -match '^\s*data_dir\s*=' } |
        Select-Object -First 1
    if (-not $line) { return $fallback }
    $raw = ($line -split '=', 2)[1].Trim()
    if ([string]::IsNullOrWhiteSpace($raw)) { return $fallback }
    if ([System.IO.Path]::IsPathRooted($raw)) { return $raw }
    return (Join-Path $PackageRoot $raw)
}

$oldDir = $null
try {
    # 归一化：.bat 传进来的可能是 `C:\path\xgame\.` 这种带尾点的形式，
    # 不 resolve 的话后面对它取 Parent 会得到包目录自己，交换目录那一步就全错了
    $Root = (Resolve-Path -LiteralPath $Root).Path

    $versionFile = Join-Path $Root 'version.txt'
    $current = if (Test-Path $versionFile) { (Get-Content -LiteralPath $versionFile -Raw).Trim() } else { 'v0.0.0' }
    Write-Step "当前版本：$current"

    # ---------- 1. 找更新的安装包 ----------
    $folders = @((Join-Path $Root 'updates'), $Root, (Split-Path $Root -Parent))
    $best = $null
    $bestVersion = $null
    foreach ($folder in $folders) {
        if (-not (Test-Path $folder)) { continue }
        $zips = Get-ChildItem -LiteralPath $folder -Filter 'xgame_v*.zip' -File -ErrorAction SilentlyContinue
        foreach ($file in $zips) {
            if ($file.Name -match '^xgame_(v[0-9A-Za-z\.\-]+)\.zip$') {
                $version = $Matches[1]
                if ((Compare-Version $version $current) -gt 0) {
                    if (($null -eq $bestVersion) -or ((Compare-Version $version $bestVersion) -gt 0)) {
                        $best = $file
                        $bestVersion = $version
                    }
                }
            }
        }
    }
    if ($null -eq $best) {
        Write-Step "没有找到更新的安装包，已经是最新版本（$current）。"
        exit 0
    }
    Write-Step "找到新版本 $bestVersion ：$($best.FullName)"

    # ---------- 2. 让服务优雅退出 ----------
    $runtime = Join-Path $Root 'runtime'
    $portFile = Join-Path $runtime 'port.txt'
    $tokenFile = Join-Path $runtime 'control.token'
    $pidFile = Join-Path $runtime 'xgame.pid'
    $port = 0
    if (Test-Path $portFile) { $port = [int]((Get-Content -LiteralPath $portFile -Raw).Trim()) }

    if ($port -gt 0 -and (Test-PortOpen $port)) {
        Write-Step '正在请求服务退出……'
        if (Test-Path $tokenFile) {
            $token = (Get-Content -LiteralPath $tokenFile -Raw).Trim()
            try {
                Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/local/shutdown" -Method Post `
                    -Headers @{ 'X-XGame-Token' = $token } -TimeoutSec 10 -UseBasicParsing | Out-Null
            }
            catch {
                Write-Step "优雅退出的请求没成功（$($_.Exception.Message)），稍后改用强制结束。"
            }
        }
        $deadline = (Get-Date).AddSeconds(30)
        while ((Test-PortOpen $port) -and ((Get-Date) -lt $deadline)) { Start-Sleep -Milliseconds 300 }
        if (Test-PortOpen $port) {
            Write-Step '服务 30 秒内没有退出，强制结束进程。'
            if (Test-Path $pidFile) {
                $targetPid = [int]((Get-Content -LiteralPath $pidFile -Raw).Trim())
                try { Stop-Process -Id $targetPid -Force -ErrorAction Stop }
                catch { Write-Step "结束进程失败：$($_.Exception.Message)" }
                Start-Sleep -Seconds 2
            }
        }
    }
    else {
        Write-Step '服务当前没有在运行，直接升级。'
    }

    # ---------- 3. 解压到旁边的暂存目录 ----------
    $parent = Split-Path $Root -Parent
    $staging = Join-Path $parent ('.xgame-update-' + $bestVersion)
    if (Test-Path $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    New-Item -ItemType Directory -Path $staging | Out-Null
    Write-Step "正在解压……（$( [math]::Round($best.Length / 1MB, 1) ) MB，请稍候）"
    $tar = Join-Path $env:SystemRoot 'System32\tar.exe'
    if (Test-Path $tar) {
        & $tar -xf $best.FullName -C $staging
    }
    else {
        Expand-Archive -LiteralPath $best.FullName -DestinationPath $staging -Force
    }

    $newRoot = Join-Path $staging 'xgame'
    $stagingIsRoot = $false
    if (-not (Test-Path (Join-Path $newRoot 'launcher.py'))) {
        if (Test-Path (Join-Path $staging 'launcher.py')) {
            # 包内不是以 xgame/ 为顶层（手工打的包），把暂存目录本身当成包根
            $newRoot = $staging
            $stagingIsRoot = $true
        }
        else {
            throw "新包里找不到 launcher.py，这不像是完整的一份安装包。"
        }
    }

    # ---------- 4. 数据和配置搬过去（数据目录原地不动的那份就什么都不做）----------
    $ini = Join-Path $Root 'xgame.ini'
    if (Test-Path $ini) { Copy-Item -LiteralPath $ini -Destination (Join-Path $newRoot 'xgame.ini') -Force }

    $rootFull = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\')
    $dataDir = Get-ConfiguredDataDir $Root
    if (Test-Path $dataDir) {
        $dataFull = (Resolve-Path -LiteralPath $dataDir).Path
        if ($dataFull.StartsWith($rootFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
            $relative = $dataFull.Substring($rootFull.Length).TrimStart('\')
            $target = Join-Path $newRoot $relative
            New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
            if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
            Write-Step "正在把数据目录搬进新包：$dataFull"
            Move-Item -LiteralPath $dataFull -Destination $target
        }
        else {
            Write-Step "数据目录在包外面（$dataFull），保持不动。"
        }
    }
    else {
        Write-Step '还没有数据目录，跳过。'
    }

    # ---------- 5. 整个目录交换 ----------
    $oldDir = Join-Path $parent ('xgame-old-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Write-Step '正在替换程序文件……'
    Move-Item -LiteralPath $Root -Destination $oldDir
    try {
        Move-Item -LiteralPath $newRoot -Destination $Root
    }
    catch {
        Move-Item -LiteralPath $oldDir -Destination $Root   # 没换成，先把旧的挪回去
        throw
    }
    if (-not $stagingIsRoot) { Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue }

    # ---------- 6. 检查新版本是不是完整，然后重启 ----------
    $missing = @()
    foreach ($item in @('launcher.py', 'python\python.exe', 'web\index.html', 'backend\asgi.py')) {
        if (-not (Test-Path (Join-Path $Root $item))) { $missing += $item }
    }
    if ($missing.Count -gt 0) {
        Write-Step "新版本缺少这些文件：$($missing -join '、')"
        Write-Step "为稳妥起见保留旧版本：$oldDir（数据目录已在新包里，没有被改动）"
        Start-Process -FilePath (Join-Path $Root '启动游戏平台.cmd') -WorkingDirectory $Root
        exit 1
    }

    Remove-Item -LiteralPath $oldDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $oldDir) {
        Write-Step "旧版本没能删掉（可能被杀软占用），可以直接手动删除：$oldDir"
    }

    Write-Step ''
    Write-Step "升级完成：$current → $bestVersion，正在重新启动……"
    Start-Process -FilePath (Join-Path $Root '启动游戏平台.cmd') -WorkingDirectory $Root
    exit 0
}
catch {
    Write-Host ''
    Write-Host "升级失败：$($_.Exception.Message)" -ForegroundColor Red
    Write-Host "数据目录没有被改动。若程序文件已被挪走，它在这里：$oldDir"
    exit 1
}
