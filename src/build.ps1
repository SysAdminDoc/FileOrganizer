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
$MSBuild = "C:\Program Files\Microsoft Visual Studio\18\Community\MSBuild\Current\Bin\amd64\MSBuild.exe"

if (-not (Test-Path $MSBuild)) {
    throw "VS 2026 MSBuild not found at $MSBuild. Install Visual Studio 2026 Community."
}

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
