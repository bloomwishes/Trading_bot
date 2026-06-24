# install_prerequisites.ps1
# Requires -RunAsAdministrator

# Set ErrorActionPreference to stop on errors
$ErrorActionPreference = "Stop"

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "   AutoTrader Pro - Prerequisites Installer (Windows) " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

# Check for Administrator privileges
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "[INFO] Re-launching script as Administrator..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# Helper function to download and install a package
function Install-Software {
    param (
        [string]$Name,
        [string]$CheckCommand,
        [string]$WingetId,
        [string]$DownloadUrl,
        [string]$InstallerPath,
        [string]$SilentArgs
    )

    Write-Host "Checking for $($Name)..." -ForegroundColor White

    # Check if already installed
    if ($CheckCommand) {
        $pathCheck = Get-Command $CheckCommand -ErrorAction SilentlyContinue
        if ($pathCheck) {
            Write-Host "[OK] $($Name) is already installed." -ForegroundColor Green
            return
        }
    }

    Write-Host "[INFO] $($Name) not found. Starting installation..." -ForegroundColor Yellow

    # Try installing via winget first
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "Attempting to install $($Name) via Windows Package Manager (winget)..." -ForegroundColor Gray
        try {
            # Run winget
            $process = Start-Process winget -ArgumentList "install -e --id $WingetId --silent --accept-package-agreements --accept-source-agreements" -NoNewWindow -Wait -PassThru
            
            # Check if it succeeded
            if ($CheckCommand) {
                # Refresh path variables to check
                $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
                $pathCheck = Get-Command $CheckCommand -ErrorAction SilentlyContinue
                if ($pathCheck) {
                    Write-Host "[OK] Successfully installed $($Name) via winget." -ForegroundColor Green
                    return
                }
            }
        } catch {
            Write-Host "[WARN] winget installation failed for $($Name). Falling back to direct download." -ForegroundColor Yellow
        }
    }

    # Fallback to downloading installer
    Write-Host "Downloading $($Name) from $($DownloadUrl)..." -ForegroundColor Gray
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $InstallerPath -UseBasicParsing
    } catch {
        Write-Host "[ERROR] Failed to download $($Name): $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }

    Write-Host "Installing $($Name) silently..." -ForegroundColor Gray
    try {
        $process = Start-Process -FilePath $InstallerPath -ArgumentList $SilentArgs -NoNewWindow -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            Write-Host "[WARN] Installer returned non-zero exit code: $($process.ExitCode)" -ForegroundColor Yellow
        }
        
        # Clean up installer
        if (Test-Path $InstallerPath) {
            Remove-Item $InstallerPath -Force
        }
        
        Write-Host "[OK] Installed $($Name)." -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] Failed to run installer for $($Name): $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

# 1. Install Git
Install-Software -Name "Git" -CheckCommand "git" -WingetId "Git.Git" -DownloadUrl "https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe" -InstallerPath "$env:TEMP\GitSetup.exe" -SilentArgs "/VERYSILENT /NORESTART /NOCANCEL /SP-"

# 2. Install Python 3.10
Install-Software -Name "Python" -CheckCommand "python" -WingetId "Python.Python.3.10" -DownloadUrl "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe" -InstallerPath "$env:TEMP\PythonSetup.exe" -SilentArgs "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0"

# 3. Install Node.js
Install-Software -Name "Node.js" -CheckCommand "node" -WingetId "OpenJS.NodeJS.LTS" -DownloadUrl "https://nodejs.org/dist/v20.11.1/node-v20.11.1-x64.msi" -InstallerPath "$env:TEMP\NodeSetup.msi" -SilentArgs "/qn /norestart"

# 4. Install Ollama
Install-Software -Name "Ollama" -CheckCommand "ollama" -WingetId "Ollama.Ollama" -DownloadUrl "https://ollama.com/download/OllamaSetup.exe" -InstallerPath "$env:TEMP\OllamaSetup.exe" -SilentArgs "/silent"

# Refresh path for the current process
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

Write-Host ""
Write-Host "======================================================" -ForegroundColor Green
Write-Host "   Prerequisites Installed Successfully!              " -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Note: You may need to close and reopen your terminal or restart your PC" -ForegroundColor Yellow
Write-Host "for all new environment variables (PATH) to take effect." -ForegroundColor Yellow
Write-Host ""
Write-Host "Launching AutoTrader Pro Setup Script now..." -ForegroundColor Cyan

# Start setup.bat in the script directory
$ScriptDir = Split-Path -Parent $PSCommandPath
cd $ScriptDir
cmd.exe /c "$ScriptDir\setup.bat"
