# One-time setup for RallyBook video analysis (Windows, NVIDIA GPU).
# Run from the rallybook folder:  powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) { python -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
& $py -m pip install -r requirements.txt

# TrackNetV3 (MIT licence) for shuttle tracking
if (-not (Test-Path third_party\TrackNetV3)) {
    New-Item -ItemType Directory -Force third_party | Out-Null
    git clone --depth 1 https://github.com/qaz812345/TrackNetV3.git third_party\TrackNetV3
}
$ckpt = "models\tracknetv3"
if (-not (Test-Path "$ckpt\TrackNet_best.pt")) {
    New-Item -ItemType Directory -Force $ckpt | Out-Null
    & $py -m gdown 1CfzE87a0f6LhBp0kniSl1-89zaLCZ8cA -O "$ckpt\ckpts.zip"
    Expand-Archive -Force "$ckpt\ckpts.zip" $ckpt
    Get-ChildItem -Recurse $ckpt -Filter *.pt | Where-Object { $_.DirectoryName -ne (Resolve-Path $ckpt).Path } | Move-Item -Destination $ckpt -Force
    Remove-Item "$ckpt\ckpts.zip"
}

# YOLO26 pose weights (downloaded by Ultralytics on first use; fetch now so the first run is quick)
& $py -c "import os; os.chdir('models'); from ultralytics import YOLO; YOLO('yolo26m-pose.pt')"

& $py -c "import torch; print('CUDA available:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
Write-Host "Setup complete. Double-click start.bat to run RallyBook."
