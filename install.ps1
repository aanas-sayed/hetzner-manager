# Install hw (Hetzner Workspace Manager)
# Usage: powershell -c "irm https://raw.githubusercontent.com/aanas-sayed/hetzner-manager/main/install.ps1 | iex"

$ErrorActionPreference = "Stop"

$Repo       = "aanas-sayed/hetzner-manager"
$InstallDir = if ($env:HW_INSTALL_DIR) { $env:HW_INSTALL_DIR } else { "$env:LOCALAPPDATA\hw" }

# ── Detect arch ───────────────────────────────────────────────────────────────

$Arch = if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq "X64") {
    "x86_64"
} else {
    Write-Error "Unsupported architecture: $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)"
    exit 1
}

# ── Fetch latest version ──────────────────────────────────────────────────────

$Release = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest"
$Version = $Release.tag_name

if (-not $Version) {
    Write-Error "Could not determine latest release version."
    exit 1
}

# ── Download & extract ────────────────────────────────────────────────────────

$Filename = "hw-$Version-windows-$Arch.zip"
$Url      = "https://github.com/$Repo/releases/download/$Version/$Filename"

Write-Host "Installing hw $Version (windows/$Arch)..."

$Tmp = Join-Path $env:TEMP ([System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $Tmp | Out-Null

try {
    $ZipPath = Join-Path $Tmp $Filename
    Invoke-WebRequest $Url -OutFile $ZipPath
    Expand-Archive $ZipPath -DestinationPath $Tmp

    # ── Install ───────────────────────────────────────────────────────────────

    if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }
    Move-Item (Join-Path $Tmp "hw") $InstallDir

} finally {
    Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue
}

# ── Add to user PATH if not already present ───────────────────────────────────

$UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($UserPath -notlike "*$InstallDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$InstallDir;$UserPath", "User")
    Write-Host "Added $InstallDir to your PATH."
}

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "hw $Version installed to $InstallDir\hw.exe"
Write-Host "Restart your terminal, then run: hw"
