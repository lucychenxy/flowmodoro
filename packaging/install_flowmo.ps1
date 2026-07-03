$ErrorActionPreference = "Stop"

$installDir = Join-Path $env:LOCALAPPDATA "Programs\Flowmo"
$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Flowmo"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Flowmo.lnk"
$startMenuShortcut = Join-Path $startMenuDir "Flowmo.lnk"
$sourceExe = Join-Path $PSScriptRoot "Flowmo.exe"
$targetExe = Join-Path $installDir "Flowmo.exe"

New-Item -ItemType Directory -Force -Path $installDir | Out-Null
New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null

Copy-Item -LiteralPath $sourceExe -Destination $targetExe -Force

$shell = New-Object -ComObject WScript.Shell
foreach ($shortcutPath in @($desktopShortcut, $startMenuShortcut)) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetExe
    $shortcut.WorkingDirectory = $installDir
    $shortcut.Description = "Flowmo Flowmodoro timer"
    $shortcut.Save()
}

Start-Process -FilePath $targetExe -WorkingDirectory $installDir
