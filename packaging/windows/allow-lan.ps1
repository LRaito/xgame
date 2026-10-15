<#
允许局域网访问：给 Windows 防火墙加一条**只放行这个包里的 python.exe** 的入站规则。

需要管理员权限，由「允许局域网访问.bat」通过 UAC 提权调起。规则只对「专用网络」生效
（家里/公司的 Wi-Fi 属于这一类，公共网络不放行），也刻意不写成 `python.exe` 通配——
不然这台机器上任何 Python 程序都能被外网连。

重复运行不会堆规则：先按名字删掉旧的再加。
#>
param(
    [Parameter(Mandatory = $true)][string]$Root
)

$Root = (Resolve-Path -LiteralPath $Root).Path
$exe = Join-Path $Root 'python\python.exe'
if (-not (Test-Path $exe)) {
    Write-Host "找不到 $exe，这个包似乎不完整。" -ForegroundColor Red
    exit 1
}

& netsh advfirewall firewall delete rule name="XGame" | Out-Null
& netsh advfirewall firewall add rule name="XGame" dir=in action=allow program="$exe" enable=yes profile=private
if ($LASTEXITCODE -ne 0) {
    Write-Host '添加防火墙规则失败。' -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ''
Write-Host '已放行：同一 Wi-Fi 下的手机、平板现在可以访问这个站点。' -ForegroundColor Green
Write-Host '地址形如 http://<这台电脑的局域网IP>:8910 —— 启动窗口里会把它打出来。'
Write-Host '取消放行：netsh advfirewall firewall delete rule name="XGame"（管理员）'
