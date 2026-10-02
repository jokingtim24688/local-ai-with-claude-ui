# Night Crew — install abliterated models, then rank them in the app.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_abliterated_models.ps1
#
# Every repo and file name below was checked on Hugging Face. Each model is downloaded
# as Q4_K_M (~5 GB), then registered with Ollama using the matching official chat
# template, because a bare GGUF often has no tool-calling template and the whole point
# of this is tool calling. Re-running skips what you already have.
#
#   -Only llama31-abl,qwen25-abl   install just those
#   -Dest D:\models                download somewhere with room
#   -List                          show the table and exit

param(
  [string]$Dest = "$HOME\Downloads\nightcrew-models",
  [string[]]$Only = @(),
  [switch]$List
)

$ErrorActionPreference = "Stop"

# name           = what it is called in Ollama / the app
# template       = official Ollama model whose chat template matches (pulled if missing)
$Models = @(
  @{ name="llama31-abl";        template="llama3.1:8b";   gb=4.9
     repo="mlabonne/Meta-Llama-3.1-8B-Instruct-abliterated-GGUF"
     file="meta-llama-3.1-8b-instruct-abliterated.Q4_K_M.gguf"
     note="Llama 3.1 8B Instruct, Meta-trained for tool use. Start here." }

  @{ name="llama31-abl-i1";     template="llama3.1:8b";   gb=4.9
     repo="mradermacher/Meta-Llama-3.1-8B-Instruct-abliterated-i1-GGUF"
     file="Meta-Llama-3.1-8B-Instruct-abliterated.i1-Q4_K_M.gguf"
     note="Same model, imatrix quant (often a touch sharper)." }

  @{ name="llama31-obliteratus"; template="llama3.1:8b";  gb=4.9
     repo="mradermacher/Llama-3.1-8B-Instruct-abliterated-obliteratus-i1-GGUF"
     file="Llama-3.1-8B-Instruct-abliterated-obliteratus.i1-Q4_K_M.gguf"
     note="Llama 3.1 8B, a different abliteration method." }

  @{ name="qwen25-abl";         template="qwen2.5:7b";    gb=4.7
     repo="mradermacher/Qwen2.5-7B-Instruct-abliterated-v2-i1-GGUF"
     file="Qwen2.5-7B-Instruct-abliterated-v2.i1-Q4_K_M.gguf"
     note="Qwen2.5 7B INSTRUCT (not the coder). Solid tool caller." }

  @{ name="qwen3-huihui-abl";   template="qwen3:8b";      gb=5.0
     repo="mradermacher/Huihui-Qwen3-8B-abliterated-v2-GGUF"
     file="Huihui-Qwen3-8B-abliterated-v2.Q4_K_M.gguf"
     note="Qwen3 8B, huihui-ai's abliteration." }

  @{ name="qwen3-josiefied-abl"; template="qwen3:8b";     gb=5.0
     repo="bartowski/Goekdeniz-Guelmez_Josiefied-Qwen3-8B-abliterated-v1-GGUF"
     file="Goekdeniz-Guelmez_Josiefied-Qwen3-8B-abliterated-v1-Q4_K_M.gguf"
     note="Qwen3 8B, Josiefied tune." }

  @{ name="granite33-abl";      template="granite3.3:8b"; gb=4.9
     repo="mradermacher/granite-3.3-8b-instruct-abliterated-i1-GGUF"
     file="granite-3.3-8b-instruct-abliterated.i1-Q4_K_M.gguf"
     note="IBM Granite 3.3 8B, built for agent/tool workflows." }

  @{ name="lfm25-hermes-agent"; template="";              gb=5.2
     repo="DuoNeural/LFM2.5-8B-A1B-Hermes-Agentic-Coder-Abliterated-v3-GGUF"
     file="LFM2.5-8B-A1B-Hermes-Agentic-Coder-Abliterated-v3-Q4_K_M.gguf"
     note="Tagged function-calling + agentic. MoE, ~1B active, fast. Uses its own template." }

  @{ name="hermes3-abl-3b";     template="llama3.2:3b";   gb=2.0
     repo="mradermacher/Hermes-3-Llama-3.2-3B-abliterated-i1-GGUF"
     file="Hermes-3-Llama-3.2-3B-abliterated.i1-Q4_K_M.gguf"
     note="Only abliterated Hermes 3 there is. 3B — small, but Hermes is tool-trained." }

  @{ name="qwen25-coder-abl";   template="qwen2.5-coder:7b"; gb=4.7
     repo="bartowski/Qwen2.5-Coder-7B-Instruct-abliterated-GGUF"
     file="Qwen2.5-Coder-7B-Instruct-abliterated-Q4_K_M.gguf"
     note="Coder model — best as the WORKER, not the lead." }
)

if ($Only.Count) { $Models = $Models | Where-Object { $Only -contains $_.name } }

if ($List -or -not $Models.Count) {
  $Models | ForEach-Object { "{0,-22} {1,5} GB  {2}" -f $_.name, $_.gb, $_.note }
  $total = ($Models | Measure-Object -Property gb -Sum).Sum
  "`nTotal download: about $total GB"
  return
}

$total = ($Models | Measure-Object -Property gb -Sum).Sum
Write-Host "About to download $($Models.Count) models, roughly $total GB, into $Dest" -ForegroundColor Cyan
$free = [math]::Round((Get-PSDrive -Name (Split-Path -Qualifier $Dest).TrimEnd(':')).Free / 1GB, 1)
Write-Host "Free space on that drive: $free GB" -ForegroundColor Cyan
if ($free -lt ($total * 2)) {
  Write-Host "Ollama keeps its own copy, so you want roughly twice the download size free." -ForegroundColor Yellow
}
if ((Read-Host "Continue? [y/N]") -notmatch '^[Yy]') { return }

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$have = (& ollama list) -join "`n"
$done = @(); $failed = @()

foreach ($m in $Models) {
  Write-Host "`n=== $($m.name) — $($m.note)" -ForegroundColor Green
  if ($have -match [regex]::Escape($m.name)) { Write-Host "already in Ollama, skipping"; $done += $m.name; continue }

  $path = Join-Path $Dest $m.file
  if (-not (Test-Path $path)) {
    $url = "https://huggingface.co/$($m.repo)/resolve/main/$($m.file)"
    Write-Host "downloading $($m.gb) GB…"
    # curl.exe follows the CDN redirect that `ollama pull hf.co/...` refuses
    & curl.exe -L --fail --retry 3 --retry-delay 5 -C - -o "$path" $url
    if ($LASTEXITCODE -ne 0) { Write-Host "download failed" -ForegroundColor Red; $failed += $m.name; continue }
  } else { Write-Host "already downloaded" }

  # borrow the official chat template so tool calling works
  $mf = Join-Path $Dest "$($m.name).Modelfile"
  if ($m.template) {
    if ($have -notmatch [regex]::Escape($m.template)) { & ollama pull $m.template }
    (& ollama show $m.template --modelfile) -replace '^FROM .*', "FROM $path" | Set-Content $mf
  } else {
    "FROM $path" | Set-Content $mf          # model ships its own template
  }

  & ollama create $m.name -f $mf
  if ($LASTEXITCODE -eq 0) { $done += $m.name } else { $failed += $m.name }
}

Write-Host "`ninstalled: $($done -join ', ')" -ForegroundColor Green
if ($failed.Count) { Write-Host "failed:    $($failed -join ', ')" -ForegroundColor Red }
Write-Host "`nNow open Night Crew -> Customize -> Apps -> 'Rank all my models'." -ForegroundColor Cyan
Write-Host "The GGUF files in $Dest can be deleted afterwards; Ollama has its own copy."
