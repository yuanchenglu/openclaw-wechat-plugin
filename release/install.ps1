# ============================================================================
# OpenClaw 微信频道插件 - Windows PowerShell 安装脚本
# ============================================================================
#
# 使用方法：
#   irm https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main/release/install.ps1 | iex
#
# 支持系统：Windows 10/11
# ============================================================================

$VERSION = "1.2.0"
$PLUGIN_DIR = if ($env:PLUGIN_DIR) { $env:PLUGIN_DIR } else { "$env:USERPROFILE\.openclaw\wechat-channel" }
$OPENCLAW_URL = if ($env:OPENCLAW_URL) { $env:OPENCLAW_URL } else { "http://127.0.0.1:18789" }
$RELAY_URL = if ($env:RELAY_URL) { $env:RELAY_URL } else { "wss://claw-wechat.7color.vip/ws-channel" }
$INSTANCE_TYPE = if ($env:INSTANCE_TYPE) { $env:INSTANCE_TYPE } else { "bare" }

function Print-Banner {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Blue
    Write-Host "       OpenClaw 微信频道客户端 v$VERSION" -ForegroundColor Blue
    Write-Host "       让你的 AI，就在微信里" -ForegroundColor Blue
    Write-Host "============================================================" -ForegroundColor Blue
    Write-Host ""
}

function Check-Python {
    Write-Host "[1/4] 检查 Python 环境..." -ForegroundColor Blue
    
    $pythonCmd = $null
    
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $pythonCmd = "python"
    } elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
        $pythonCmd = "python3"
    }
    
    if ($pythonCmd) {
        $version = & $pythonCmd --version 2>&1
        Write-Host "✅ $version 已安装" -ForegroundColor Green
        return $pythonCmd
    }
    
    Write-Host "❌ 未找到 Python，请先安装 Python 3.8+" -ForegroundColor Red
    Write-Host "下载地址: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

function Check-Pip {
    param($PythonCmd)
    
    Write-Host "[2/4] 检查 pip..." -ForegroundColor Blue
    
    $pipCheck = & $PythonCmd -m pip --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ pip 已安装" -ForegroundColor Green
        return $true
    }
    
    Write-Host "❌ 未找到 pip，请先安装 pip" -ForegroundColor Red
    exit 1
}

function Download-Client {
    Write-Host "[3/4] 下载客户端..." -ForegroundColor Blue
    
    # 下载源列表（按优先级排序）
    $sources = @(
        "https://wechat.clawadmin.org",
        "https://raw.githubusercontent.com/yuanchenglu/openclaw-wechat-plugin/main",
        "https://claw-wechat.7color.vip"
    )
    
    # 创建目录
    if (-not (Test-Path $PLUGIN_DIR)) {
        New-Item -ItemType Directory -Path $PLUGIN_DIR -Force | Out-Null
    }
    
    # 尝试从多个源下载
    $downloaded = $false
    foreach ($baseUrl in $sources) {
        $clientUrl = "$baseUrl/plugin/src/client.py"
        $requirementsUrl = "$baseUrl/plugin/requirements.txt"
        
        try {
            Invoke-WebRequest -Uri $clientUrl -OutFile "$PLUGIN_DIR\client.py" -UseBasicParsing -TimeoutSec 30
            Invoke-WebRequest -Uri $requirementsUrl -OutFile "$PLUGIN_DIR\requirements.txt" -UseBasicParsing -TimeoutSec 30
            Write-Host "✅ 客户端已下载到: $PLUGIN_DIR (来源: $baseUrl)" -ForegroundColor Green
            $downloaded = $true
            break
        }
        catch {
            Write-Host "  ⚠️ $baseUrl 下载失败，尝试下一个源..." -ForegroundColor Yellow
        }
    }
    
    if (-not $downloaded) {
        Write-Host "❌ 所有下载源均失败，请检查网络连接" -ForegroundColor Red
        exit 1
    }
}

function Install-Dependencies {
    param($PythonCmd)
    
    Write-Host "[4/4] 安装依赖..." -ForegroundColor Blue
    
    Push-Location $PLUGIN_DIR
    try {
        & $PythonCmd -m pip install -q websockets httpx 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ 依赖已安装" -ForegroundColor Green
        } else {
            Write-Host "❌ 依赖安装失败" -ForegroundColor Red
            exit 1
        }
    }
    finally {
        Pop-Location
    }
}

function Create-Launcher {
    param($PythonCmd)
    
    # start.ps1
    $startScript = @"
`$env:OPENCLAW_URL = if (`$env:OPENCLAW_URL) { `$env:OPENCLAW_URL } else { "$OPENCLAW_URL" }
`$env:RELAY_URL = if (`$env:RELAY_URL) { `$env:RELAY_URL } else { "$RELAY_URL" }
`$env:INSTANCE_TYPE = if (`$env:INSTANCE_TYPE) { `$env:INSTANCE_TYPE } else { "$INSTANCE_TYPE" }

Write-Host "OpenClaw 微信频道客户端 v$VERSION"
Write-Host "OpenClaw: `$env:OPENCLAW_URL"
Write-Host "中转服务: `$env:RELAY_URL"

Set-Location "$PLUGIN_DIR"
& $PythonCmd client.py --openclaw-url "`$env:OPENCLAW_URL" --relay-url "`$env:RELAY_URL" --instance-type "`$env:INSTANCE_TYPE"
"@
    $startScript | Out-File -FilePath "$PLUGIN_DIR\start.ps1" -Encoding UTF8
    
    # stop.ps1
    $stopScript = @"
Get-Process -Name python* -ErrorAction SilentlyContinue | Where-Object { `$_.CommandLine -like "*client.py*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "客户端已停止"
"@
    $stopScript | Out-File -FilePath "$PLUGIN_DIR\stop.ps1" -Encoding UTF8
    
    # uninstall.ps1
    $uninstallScript = @"
Remove-Item -Path "$PLUGIN_DIR" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "已卸载"
"@
    $uninstallScript | Out-File -FilePath "$PLUGIN_DIR\uninstall.ps1" -Encoding UTF8
    
    Write-Host "✅ 启动脚本已创建" -ForegroundColor Green
}

function Print-Completion {
    Write-Host ""
    Write-Host "✅ 安装完成！" -ForegroundColor Green
    Write-Host ""
    Write-Host "使用方法："
    Write-Host "  PowerShell:  $PLUGIN_DIR\start.ps1"
    Write-Host "  CMD:         powershell -File $PLUGIN_DIR\start.ps1"
    Write-Host ""
}

# 主流程
Print-Banner
$pythonCmd = Check-Python
Check-Pip -PythonCmd $pythonCmd
Download-Client
Install-Dependencies -PythonCmd $pythonCmd
Create-Launcher -PythonCmd $pythonCmd
Print-Completion