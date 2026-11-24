# Windows' own OCR (no install). -List: a text file with one image path per line. -Out: JSON lines {"path","text"} (UTF-8).
param([Parameter(Mandatory)][string]$List, [Parameter(Mandatory)][string]$Out, [string]$Lang = "")
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
[void][Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
[void][Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Wait-Op($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait() | Out-Null; $t.Result }
if ($Lang) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($Lang)) }
else { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if (-not $engine) { throw "no OCR language pack for '$Lang'" }
$w = New-Object System.IO.StreamWriter($Out, $false, (New-Object System.Text.UTF8Encoding($false)))
try {
  foreach ($p in [System.IO.File]::ReadAllLines($List)) {
    if (-not $p) { continue }
    $file = Wait-Op ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p)) ([Windows.Storage.StorageFile])
    $stream = Wait-Op ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $dec = Wait-Op ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bmp = Wait-Op ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $res = Wait-Op ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
    $text = ($res.Lines | ForEach-Object { $_.Text }) -join "`n"
    $w.WriteLine((@{ path = $p; text = $text } | ConvertTo-Json -Compress))
    $stream.Dispose()
  }
} finally { $w.Close() }
