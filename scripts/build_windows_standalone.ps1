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
$SourceInputDir = Join-Path $WorkspaceDir '260508_Musashino_採用医薬品'
$SourceReferenceDir = Join-Path $WorkspaceDir '旧採用医薬品リスト'
$ReleaseNotesTemplate = Join-Path $ProjectDir 'docs\templates\release-assets\RELEASE_NOTES_TEMPLATE.md'
$SkipDataBundle = $env:PHARMALIST_SKIP_DATA_BUNDLE -eq '1'

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
if (-not $SkipDataBundle) {
  if (-not (Test-Path $SourceInputDir)) {
    throw "Input directory not found: $SourceInputDir"
  }
  if (-not (Test-Path $SourceReferenceDir)) {
    throw "Reference directory not found: $SourceReferenceDir"
  }
  Copy-Item -Recurse -Force $SourceInputDir "$FinalAppDir\260508_Musashino_採用医薬品"
  Copy-Item -Recurse -Force $SourceReferenceDir "$FinalAppDir\旧採用医薬品リスト"
} else {
  New-Item -ItemType Directory -Force -Path "$FinalAppDir\260508_Musashino_採用医薬品\references" | Out-Null
  New-Item -ItemType Directory -Force -Path "$FinalAppDir\旧採用医薬品リスト" | Out-Null
}
Copy-Item -Force "$ProjectDir\README.md" "$FinalAppDir\README.md"
Copy-Item -Force $ReleaseNotesTemplate "$FinalAppDir\RELEASE_NOTES_TEMPLATE.md"
New-Item -ItemType Directory -Force -Path $DocsDir | Out-Null
Copy-Item -Force "$ProjectDir\docs\requirements-spec.html" "$DocsDir\requirements-spec.html"
Copy-Item -Force "$ProjectDir\docs\windows-distribution-guide.md" "$DocsDir\windows-distribution-guide.md"

if (Test-Path $ZipPath) {
  Remove-Item -Force $ZipPath
}
Compress-Archive -Path $FinalAppDir -DestinationPath $ZipPath

Write-Host "Windows standalone directory: $FinalAppDir"
Write-Host "Windows standalone zip: $ZipPath"
if ($SkipDataBundle) {
  Write-Host "Data bundle skipped: placeholder input/reference directories were created for CI packaging."
}