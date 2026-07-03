param(
    [string]$Version = "v.0.0.1"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$distDir = Join-Path $root "dist"
$releaseDir = Join-Path $root "release"
$stagingDir = Join-Path $releaseDir "installer-staging"
$sedPath = Join-Path $releaseDir "Flowmo-$Version.sed"
$installerPath = Join-Path $releaseDir "Flowmo-Setup-$Version.exe"
$flowmoExe = Join-Path $distDir "Flowmo.exe"
$installScript = Join-Path $PSScriptRoot "install_flowmo.ps1"

if (-not (Test-Path -LiteralPath $flowmoExe)) {
    throw "Missing $flowmoExe. Build it first with: conda run -n flowmo pyinstaller --noconfirm --clean Flowmo.spec"
}

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
if (Test-Path -LiteralPath $stagingDir) {
    $resolvedStaging = Resolve-Path -LiteralPath $stagingDir
    $resolvedRelease = Resolve-Path -LiteralPath $releaseDir
    if (-not $resolvedStaging.Path.StartsWith($resolvedRelease.Path)) {
        throw "Refusing to remove staging path outside release directory: $resolvedStaging"
    }
    Remove-Item -LiteralPath $stagingDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null

Copy-Item -LiteralPath $flowmoExe -Destination (Join-Path $stagingDir "Flowmo.exe") -Force
Copy-Item -LiteralPath $installScript -Destination (Join-Path $stagingDir "install_flowmo.ps1") -Force

$sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles

[Strings]
InstallPrompt=Install Flowmo ${Version}?
FinishMessage=Flowmo has been installed.
TargetName=$installerPath
FriendlyName=Flowmo $Version Installer
AppLaunched=powershell.exe -ExecutionPolicy Bypass -NoProfile -File install_flowmo.ps1
FILE0="Flowmo.exe"
FILE1="install_flowmo.ps1"

[SourceFiles]
SourceFiles0=$stagingDir\

[SourceFiles0]
%FILE0%=
%FILE1%=
"@

Set-Content -LiteralPath $sedPath -Value $sed -Encoding ASCII
& iexpress.exe /N /Q $sedPath | Out-Null

if (-not (Test-Path -LiteralPath $installerPath)) {
    throw "Installer was not created: $installerPath"
}

Get-Item -LiteralPath $installerPath
