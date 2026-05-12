$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$WorkspaceDir = Split-Path -Parent $ProjectDir
$AppName = '薬剤リスト変換アプリ'
$ReleaseName = 'windows-standalone-release'
$DistDir = Join-Path $ProjectDir 'dist'
$ReleaseDir = Join-Path $DistDir $ReleaseName
$PyInstallerRoot = Join-Path $ProjectDir '.tmp\pyinstaller-windows-standalone'
$PyInstallerDist = Join-Path $PyInstallerRoot 'dist'
$PyInstallerBuild = Join-Path $PyInstallerRoot 'build'
$BuiltAppDir = Join-Path $PyInstallerDist $AppName
$FinalAppDir = Join-Path $ReleaseDir $AppName
$DocsDir = Join-Path $FinalAppDir 'docs'
$ZipPath = Join-Path $DistDir "$AppName-standalone-windows.zip"
$ReleaseNotesTemplate = Join-Path $ProjectDir 'docs\templates\release-assets\RELEASE_NOTES_TEMPLATE.md'
$SignEnabled = $env:WINDOWS_SIGN_ENABLED -eq '1'
$CertificatePath = $env:WINDOWS_CERT_PFX_PATH
$CertificatePassword = $env:WINDOWS_CERT_PFX_PASSWORD
$TimestampUrl = $env:WINDOWS_TIMESTAMP_URL

Remove-Item -Recurse -Force $ReleaseDir, $PyInstallerRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $ReleaseDir, $PyInstallerRoot | Out-Null

python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --onedir `
  --name "$AppName" `
  --distpath "$PyInstallerDist" `
  --workpath "$PyInstallerBuild" `
  --specpath "$PyInstallerRoot" `
  --paths "$ProjectDir\src" `
  "$ProjectDir\packaging\windows\standalone_launcher.py"

Copy-Item -Recurse -Force $BuiltAppDir $FinalAppDir
Copy-Item -Recurse -Force "$ProjectDir\config" "$FinalAppDir\config"
Copy-Item -Force "$ProjectDir\README.md" "$FinalAppDir\README.md"
Copy-Item -Force $ReleaseNotesTemplate "$FinalAppDir\RELEASE_NOTES_TEMPLATE.md"
New-Item -ItemType Directory -Force -Path $DocsDir | Out-Null
Copy-Item -Force "$ProjectDir\docs\requirements-spec.html" "$DocsDir\requirements-spec.html"
Copy-Item -Force "$ProjectDir\docs\windows-distribution-guide.md" "$DocsDir\windows-distribution-guide.md"

if ($SignEnabled) {
  if ([string]::IsNullOrWhiteSpace($CertificatePath) -or -not (Test-Path $CertificatePath)) {
    throw 'WINDOWS_CERT_PFX_PATH が未設定、または証明書ファイルが存在しません。'
  }
  if ([string]::IsNullOrWhiteSpace($CertificatePassword)) {
    throw 'WINDOWS_CERT_PFX_PASSWORD が未設定です。'
  }
  if ([string]::IsNullOrWhiteSpace($TimestampUrl)) {
    throw 'WINDOWS_TIMESTAMP_URL が未設定です。'
  }

  $SignTool = Get-Command signtool.exe -ErrorAction Stop
  $SignTargets = Get-ChildItem -Path $FinalAppDir -Recurse -File |
    Where-Object { $_.Extension -in '.exe', '.dll', '.pyd' }

  foreach ($Target in $SignTargets) {
    & $SignTool.Source sign /fd SHA256 /td SHA256 /tr $TimestampUrl /f $CertificatePath /p $CertificatePassword $Target.FullName
    if ($LASTEXITCODE -ne 0) {
      throw "signtool failed: $($Target.FullName)"
    }

    $Signature = Get-AuthenticodeSignature -FilePath $Target.FullName
    if ($Signature.Status -ne 'Valid') {
      throw "Authenticode verification failed: $($Target.FullName) status=$($Signature.Status)"
    }
  }
}

if (Test-Path $ZipPath) {
  Remove-Item -Force $ZipPath
}
Compress-Archive -Path $FinalAppDir -DestinationPath $ZipPath

Write-Host "Windows standalone directory: $FinalAppDir"
Write-Host "Windows standalone zip: $ZipPath"