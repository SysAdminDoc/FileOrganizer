<#
.SYNOPSIS
    Build FileOrganizer.UI (WinUI 3 shell)

.DESCRIPTION
    Wraps VS MSBuild to avoid the bare-dotnet AppX/PRI task failure on
    .NET 10 SDK + WindowsAppSDK 1.5. Cleans obj/bin first to avoid the
    MarkupCompilePass2 stale-state cascade.

.EXAMPLE
    pwsh src/build.ps1
    pwsh src/build.ps1 -Configuration Release
#>

param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Debug",
    [ValidateSet("x64", "arm64")]
    [string]$Platform = "x64"
)

$ErrorActionPreference = "Stop"

$ProjectPath = Join-Path $PSScriptRoot "FileOrganizer.UI" "FileOrganizer.UI.csproj"
$msbuildCandidates = @()

# Honor an explicit CI/developer override first, then use Microsoft's
# installation locator when available.  The final filesystem scan covers
# Build Tools installs where vswhere is not on PATH.
$explicitMsBuild = [Environment]::GetEnvironmentVariable("MSBUILD_EXE_PATH")
if (-not [string]::IsNullOrWhiteSpace($explicitMsBuild)) {
    $msbuildCandidates += $explicitMsBuild
}

$vswhere = $null
if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
}
if ($vswhere -and (Test-Path $vswhere -PathType Leaf)) {
    $located = & $vswhere -latest -products * -requires Microsoft.Component.MSBuild `
        -find "MSBuild\**\Bin\amd64\MSBuild.exe" 2>$null
    if ($located) { $msbuildCandidates += $located }
}

$pathMsBuild = Get-Command "MSBuild.exe" -ErrorAction SilentlyContinue
if ($pathMsBuild) { $msbuildCandidates += $pathMsBuild.Source }

$visualStudioRoots = @(${env:ProgramFiles}, ${env:ProgramFiles(x86)}) |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    ForEach-Object { Join-Path $_ "Microsoft Visual Studio" }
foreach ($root in $visualStudioRoots) {
    if (-not (Test-Path $root -PathType Container)) { continue }
    $msbuildCandidates += Get-ChildItem -Path $root -Filter "MSBuild.exe" -File -Recurse `
        -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\MSBuild\\Current\\Bin(\\amd64)?\\MSBuild\.exe$" } |
        Sort-Object FullName |
        Select-Object -ExpandProperty FullName
}

$MSBuild = $msbuildCandidates |
    Where-Object { $_ -and (Test-Path $_ -PathType Leaf) } |
    Select-Object -First 1
if (-not $MSBuild) {
    throw "MSBuild was not found. Install Visual Studio/Build Tools with the MSBuild component or set MSBUILD_EXE_PATH to a compatible MSBuild.exe."
}
$msbuildBin = Split-Path $MSBuild -Parent
$sdkResolver = Join-Path $msbuildBin "SdkResolvers\Microsoft.DotNet.MSBuildSdkResolver.dll"
if (-not (Test-Path $sdkResolver -PathType Leaf)) {
    throw "MSBuild was found at $MSBuild, but its .NET SDK resolver is missing. Install the Visual Studio .NET SDK/MSBuild workload or set MSBUILD_EXE_PATH to a complete installation."
}
Write-Host "Using MSBuild: $MSBuild" -ForegroundColor DarkGray

Write-Host "== Cleaning obj/ and bin/ ==" -ForegroundColor Cyan
$projectDir = Split-Path $ProjectPath -Parent
Get-ChildItem -Path $projectDir -Include bin, obj -Recurse -Directory -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "== Restoring ($Configuration|$Platform) ==" -ForegroundColor Cyan
& $MSBuild $ProjectPath -t:Restore -p:Configuration=$Configuration -p:Platform=$Platform -v:minimal
if ($LASTEXITCODE -ne 0) { throw "Restore failed" }

Write-Host "== Building ($Configuration|$Platform) ==" -ForegroundColor Cyan
& $MSBuild $ProjectPath -t:Build -p:Configuration=$Configuration -p:Platform=$Platform -v:minimal
if ($LASTEXITCODE -ne 0) { throw "Build failed" }

$framework = "net8.0-windows10.0.19041.0"
$exe = Join-Path $projectDir "bin" $Platform $Configuration $framework "FileOrganizer.exe"
if (Test-Path $exe) {
    Write-Host "`nBuilt: $exe" -ForegroundColor Green
} else {
    Write-Warning "Build reported success but $exe was not produced."
}
