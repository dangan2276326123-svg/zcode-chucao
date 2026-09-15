param(
    [string]$PptxPath,
    [string]$OutDir
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
$pp = New-Object -ComObject PowerPoint.Application
$pres = $pp.Presentations.Open($PptxPath, $true, $false, $false)
try {
    $pres.Export($OutDir, 'PNG', 1600, 900)
    Write-Output ("EXPORTED slides=" + $pres.Slides.Count)
} finally {
    $pres.Close()
    $pp.Quit()
}
