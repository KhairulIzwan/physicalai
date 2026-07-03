# PhysicalAI Exploration — Intel Panther Lake Platform
**Date:** 2026-07-02 / 2026-07-03  
**Platform:** Intel Core Ultra 5 335 (Panther Lake) | 64 GB DDR5-6400 | GPU + NPU  
**OS:** Linux 6.17-intel | OpenVINO 2026.1 | physicalai 0.1.2.dev15

---

## 1. Environment Setup

```bash
cd /home/user/physicalai
python3 -m venv .venv
.venv/bin/pip install -e ".[realsense]"
```

Installed:
- physicalai 0.1.2.dev15
- OpenVINO 2026.1
- ONNX Runtime 1.27.0
- Intel RealSense 2.58.2
- Transformers 5.3.0

Available devices confirmed via `benchmark_app -h`:
```
Available target devices:  CPU  GPU  NPU
```

---

## 2. physicalai Inference Benchmarks

### Model: ACT FP16 (`OpenVINO/act-fp16-ov`)
**What is ACT?**  
Action Chunking with Transformers — a lightweight robot policy that predicts 100 future actions at once from camera images + robot joint state. No language input required. Fast and compact.

| Spec | Value |
|---|---|
| Model size | 69 MB |
| Inputs | state [1,8] + 2× images [1,3,256,256] |
| Output | action [1,100,7] — 100-step chunk, 7 DOF |
| Architecture | Transformer encoder-decoder |

**Benchmark Results (100 iters, GPU):**

| Device | Median | Mean | FPS | Std dev |
|---|---|---|---|---|
| CPU | 34.4 ms | 34.7 ms | 28.8 | 0.86 ms |
| **GPU** | **2.92 ms** | **2.92 ms** | **341.9** | **0.02 ms** |
| NPU | ❌ TDR hang | — | — | — |

```bash
# Re-run:
cd /home/user/physicalai
.venv/bin/python benchmark.py --model models/OpenVINO--act-fp16-ov --device GPU
```

---

### Model: Pi0.5 Libero FP16 (`OpenVINO/pi05-libero-fp16-ov`)
**What is Pi0.5?**  
Physical Intelligence's Vision-Language-Action (VLA) model. Takes a natural language task description + camera images + robot joint state and generates actions via flow matching. Much larger than ACT — includes a full language model backbone.

| Spec | Value |
|---|---|
| Model size | 6.3 GB (FP16) |
| Inputs | state [1,8] + task string (200 tokens) + 2 cameras [1,3,224,224] + 1 empty slot |
| Output | action [1,50,7] — 50-step chunk, 7 DOF |
| Architecture | Large VLA transformer + flow matching |

**Benchmark Results — FP16 (100 iters, GPU):**

| Device | Median | Mean | FPS | Std dev |
|---|---|---|---|---|
| CPU | 12,429 ms | 12,354 ms | 0.1 | 208 ms |
| **GPU** | **524.6 ms** | **524.7 ms** | **1.9** | **2.5 ms** |
| NPU | ❌ TDR hang | — | — | — |

---

### Model: Pi0.5 Libero INT8 (quantized locally with NNCF)
Quantized using NNCF 3.2.0 with 300 synthetic calibration samples targeting NPU profile.  
Quantization time: ~2h 10min on CPU. Applied SmoothQuant + FastBiasCorrection.

| Spec | Value |
|---|---|
| Model size | 3.18 GB (INT8, down from 6.3 GB FP16) |
| Size reduction | 49.5% |
| Quantization | NNCF PTQ, target=NPU, SmoothQuant + Transformer preset |

**Benchmark Results — INT8 (100 iters, GPU):**

| Device | Median | Mean | FPS | Std dev | vs FP16 |
|---|---|---|---|---|---|
| CPU | 4,556 ms | 4,561 ms | 0.2 | 15.4 ms | 2.7× faster |
| **GPU** | **361.4 ms** | **361.5 ms** | **2.8** | **0.98 ms** | **1.5× faster** |
| NPU | ❌ TDR hang | — | — | — | Still too large |

```bash
# Re-run:
cd /home/user/physicalai
.venv/bin/python benchmark.py --model models/pi05-libero-int8 --device GPU
```

---

## 3. NPU Compatibility Analysis

| Model | Size | NPU Result | Reason |
|---|---|---|---|
| MobileNet-v2 INT8 | ~4 MB | ✅ 4953 FPS | Small, fully quantized |
| YOLOv5m INT8 | ~88 MB | ✅ 387 FPS, 97% NPU util | Good NPU target |
| ACT FP16 | 69 MB | ❌ TDR hang | FP16 runtime issue |
| Pi0.5 FP16 | 6.3 GB | ❌ TDR hang | Far exceeds NPU memory |
| Pi0.5 INT8 | 3.18 GB | ❌ TDR hang | Still exceeds NPU memory |

**NPU sweet spot on PTL**: INT8 models under ~200 MB. Large VLA transformers need GPU.

**Note**: `query_model(model, 'NPU')` reports all ops as supported for all models above — this is a compile-time check only, not a runtime memory check. TDR hangs are runtime memory/timeout failures.

---

## 4. Known Issues & Workarounds

### HuggingFace Cache Symlink Issue
When loading pi0.5 directly from HF cache, `InferenceModel` throws:
```
ValueError: artifact path 'tokenizer.xml' escapes the export directory
```
**Cause**: HF cache uses symlinks pointing to `../../blobs/` which resolve outside the snapshot dir.  
**Fix**: Copy model with `-L` flag to resolve symlinks:
```bash
cp -L /path/to/hf/snapshot/*.xml *.bin *.json /home/user/physicalai/models/pi05-libero-fp16/
```

---

## 5. Scripts Created

| Script | Purpose |
|---|---|
| `benchmark.py` | Unified latency benchmark — auto-detects policy type from `manifest.json`, supports ACT, Pi0.5, and any future physicalai policy. Also handles model download. |

### Fresh Clone Workflow
After a `git clone`, no models are included. Use `benchmark.py` to discover, download and benchmark:

```bash
# 1. Set up environment (once)
cd /home/user/physicalai
python3 -m venv .venv
.venv/bin/pip install -e ".[realsense]"

# 2. List available models on HuggingFace
.venv/bin/python benchmark.py --list-models

# 3. Download a model (fetches from HuggingFace, resolves symlinks, copies to models/)
.venv/bin/python benchmark.py --model OpenVINO/act-fp16-ov --download-only
.venv/bin/python benchmark.py --model OpenVINO/pi05-libero-fp16-ov --download-only

# 4. Benchmark
.venv/bin/python benchmark.py --model models/OpenVINO--act-fp16-ov --device GPU
.venv/bin/python benchmark.py --model models/pi05-libero-int8 --device GPU

# Custom options
.venv/bin/python benchmark.py --model models/OpenVINO--act-fp16-ov --device CPU --iters 50 --warmup 5
```

---

## 6. Model Files on Disk

```
/home/user/physicalai/models/
├── OpenVINO--act-fp16-ov/    # 69 MB — ACT FP16 (copied from HF cache, symlinks resolved)
│   ├── act.xml / act.bin
│   ├── manifest.json
│   └── config.json
├── pi05-libero-fp16/         # 6.3 GB — Pi0.5 FP16, GPU only
│   ├── pi05.xml / pi05.bin
│   ├── tokenizer.xml / tokenizer.bin
│   ├── manifest.json
│   └── config.json
└── pi05-libero-int8/         # 3.18 GB — Pi0.5 INT8 quantized with NNCF, GPU only
    ├── pi05.xml / pi05.bin
    ├── tokenizer.xml / tokenizer.bin
    ├── manifest.json
    └── config.json

~/.cache/huggingface/hub/
├── models--OpenVINO--act-fp16-ov/          # original HF cache (symlinks)
└── models--OpenVINO--pi05-libero-fp16-ov/  # original HF cache (symlinks)
```
