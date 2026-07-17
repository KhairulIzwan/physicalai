#!/usr/bin/env python3
"""
physicalai Inference Latency Benchmark
Supports any exported physicalai policy model (ACT, Pi0.5, etc.)
Auto-detects policy type from manifest.json and generates appropriate dummy inputs.

Tested models:
  OpenVINO/act-fp16-ov          — ACT FP16, 69 MB
  models/pi05-libero-fp16       — Pi0.5 FP16, 6.3 GB  (GPU only)
  models/pi05-libero-int8       — Pi0.5 INT8, 3.18 GB (GPU only, NNCF quantized)

Usage:
  # ACT on GPU (recommended)
  python benchmark.py --model OpenVINO/act-fp16-ov --device GPU

  # Pi0.5 INT8 on GPU
  python benchmark.py --model models/pi05-libero-int8 --device GPU

  # From HuggingFace hub (downloads automatically)
  python benchmark.py --model OpenVINO/act-fp16-ov --device CPU --iters 50
"""

from __future__ import annotations

import argparse
import json
from itertools import repeat
from pathlib import Path
import re
import time

import numpy as np

from physicalai.inference import InferenceModel
from physicalai.inference.utils._hub import download_from_hub
from physicalai.benchmark.performance import InferenceLatencyBenchmark


# ---------------------------------------------------------------------------
# Input builders — one per policy type
# ---------------------------------------------------------------------------

def _build_act_sample() -> dict:
    """ACT: direct model-ready tensors, 256×256, no language input."""
    return {
        "state":         np.zeros((1, 8),           dtype=np.float32),
        "images.image":  np.zeros((1, 3, 256, 256), dtype=np.float32),
        "images.image2": np.zeros((1, 3, 256, 256), dtype=np.float32),
    }


def _build_pi05_sample(task: str = "pick up the block", num_cameras: int = 2) -> dict:
    """Pi0.5: raw observations fed through Pi05Preprocessor (resize + tokenize).
    2 real cameras + empty_cameras=1 from manifest → 3 total → model [3,1,3,224,224].
    """
    return {
        "images": {f"cam{i}": np.zeros((1, 3, 224, 224), dtype=np.float32)
                   for i in range(num_cameras)},
        "task":   [task],
        "state":  np.zeros((1, 8), dtype=np.float32),
    }


SAMPLE_BUILDERS = {
    "act":  _build_act_sample,
    "pi05": _build_pi05_sample,
}

NPU_LARGE_MODEL_WARNING = {
    "pi05": (
        "Pi0.5 (3.18 GB INT8 / 6.3 GB FP16) exceeds NPU memory on PTL.\n"
        "NPU TDR crash is expected. Use --device GPU instead.\n"
        "NPU works fine for small INT8 models (e.g. YOLOv5m ~88 MB)."
    ),
}


def list_available_models() -> None:
    """Search HuggingFace for physicalai-compatible models (manifest.json + OpenVINO IR)."""
    from huggingface_hub import HfApi
    from huggingface_hub.errors import HfHubHTTPError

    def _is_retryable(exc: Exception) -> bool:
        msg = str(exc).lower()
        retry_markers = ("timeout", "timed out", "503", "504", "502", "429", "tempor")
        if any(m in msg for m in retry_markers):
            return True
        code = getattr(getattr(exc, "response", None), "status_code", None)
        return code in {429, 500, 502, 503, 504}

    def _run_with_retry(callable_obj, *args, **kwargs):
        last_exc = None
        for attempt in range(1, 4):
            try:
                return callable_obj(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if not _is_retryable(exc) or attempt == 3:
                    raise
                delay = attempt
                print(f"  transient error ({exc}); retrying in {delay}s...")
                time.sleep(delay)
        raise last_exc

    api = HfApi()
    print("Searching HuggingFace for physicalai-compatible models...\n")
    candidates = []
    seen_ids = set()
    for query in ["act-fp16-ov", "pi05", "pi0-ov", "policy-ov"]:
        try:
            models = _run_with_retry(lambda: list(api.list_models(search=query, limit=20)))
        except HfHubHTTPError as exc:
            print(f"Warning: skipping query '{query}' due to server error: {exc}")
            continue
        except Exception as exc:
            print(f"Warning: skipping query '{query}' due to network error: {exc}")
            continue

        for m in models:
            if m.id in seen_ids:
                continue
            seen_ids.add(m.id)
            try:
                files = _run_with_retry(lambda: list(api.list_repo_tree(m.id)))
                file_names = [f.path for f in files]
                if "manifest.json" in file_names:
                    bin_mb = sum(f.size for f in files if f.path.endswith(".bin")) / 1e6
                    policy = next(
                        (f.path.split(".")[0] for f in files
                         if f.path.endswith(".xml") and "tokenizer" not in f.path), "?")
                    candidates.append((m.id, policy, bin_mb))
            except Exception as exc:
                print(f"  Warning: unable to inspect '{m.id}': {exc}")

    print(f"{'Repo ID':<50} {'Policy':<8} Size")
    print("-" * 72)
    for repo_id, policy, mb in sorted(candidates, key=lambda x: x[2]):
        size = f"{mb/1024:.1f} GB" if mb > 1024 else f"{mb:.0f} MB"
        print(f"{repo_id:<50} {policy:<8} {size}")
    print(f"\n{len(candidates)} model(s) found.")
    print("\nDownload with:")
    print("  .venv/bin/python benchmark.py --model <Repo ID> --download-only")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_model_path(model: str) -> Path:
    """Return a local Path — downloads from HF hub if model looks like a repo ID."""
    local = Path(model).expanduser()
    if local.exists():
        return local

    def _probably_local_reference(value: str, path: Path) -> bool:
        if path.is_absolute() or value.startswith(("./", "../", "~/")):
            return True
        if path.parts and path.parts[0] == "models":
            return True
        return path.parent != Path(".") and path.parent.exists()

    def _normalize_name(value: str) -> str:
        lowered = value.lower()
        lowered = lowered.replace("openvino--", "")
        lowered = lowered.replace("-ov", "")
        return re.sub(r"[^a-z0-9]", "", lowered)

    if _probably_local_reference(model, local):
        models_root = Path("models")
        if models_root.exists():
            requested = _normalize_name(local.name)
            candidates = []
            for d in sorted(models_root.iterdir()):
                if not d.is_dir() or not (d / "manifest.json").exists():
                    continue
                name = _normalize_name(d.name)
                if requested and (requested in name or name in requested):
                    candidates.append(d)

            if len(candidates) == 1:
                print(f"Local model not found at '{local}', using closest match: {candidates[0]}")
                return candidates[0]

            available = [str(d) for d in sorted(models_root.iterdir())
                         if d.is_dir() and (d / "manifest.json").exists()]
            msg = [
                f"Local model path not found: {local}",
                "This looks like a local path, so HuggingFace download was skipped.",
            ]
            if available:
                msg.append("Available local models:")
                msg.extend([f"  - {p}" for p in available])
            else:
                msg.append("No local exported models found under ./models")
            raise FileNotFoundError("\n".join(msg))

    # Treat as HuggingFace repo ID
    print(f"Downloading from HuggingFace: {model} ...")
    downloaded = Path(download_from_hub(model))
    # HF cache uses symlinks — copy to flat dir so physicalai path-check passes
    flat_dir = Path("models") / model.replace("/", "--")
    if not flat_dir.exists():
        import shutil
        flat_dir.mkdir(parents=True)
        for f in downloaded.iterdir():
            if f.suffix in (".xml", ".bin", ".json"):
                shutil.copy2(f, flat_dir / f.name)
        print(f"Copied to: {flat_dir}")
    return flat_dir


def detect_policy(model_path: Path) -> str:
    manifest = model_path / "manifest.json"
    if not manifest.exists():
        raise FileNotFoundError(f"manifest.json not found in {model_path}")
    return json.loads(manifest.read_text())["policy"]["name"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="physicalai inference latency benchmark (auto-detects policy type)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--model",        default=None,
                        help="Local model dir OR HuggingFace repo ID (e.g. OpenVINO/act-fp16-ov). "
                             "Required unless --list-models is used.")
    parser.add_argument("--device",       default="GPU",
                        help="OpenVINO device: CPU, GPU, NPU (default: GPU)")
    parser.add_argument("--iters",        type=int, default=100,
                        help="Measured iterations (default: 100)")
    parser.add_argument("--warmup",       type=int, default=5,
                        help="Warmup iterations (default: 5)")
    parser.add_argument("--max-duration", type=int, default=180000,
                        help="Max duration ms (default: 180000)")
    parser.add_argument("--task",         default="pick up the block",
                        help="Task string for Pi0.5 (default: 'pick up the block')")
    parser.add_argument("--download-only", action="store_true",
                        help="Download and prepare the model locally, then exit (no benchmark)")
    parser.add_argument("--list-models", action="store_true",
                        help="List all physicalai-compatible models available on HuggingFace, then exit")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.list_models:
        list_available_models()
        return

    if not args.model:
        print("Error: --model is required unless --list-models is used.")
        return

    try:
        model_path = resolve_model_path(args.model)
        policy = detect_policy(model_path)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        print(f"Error: {exc}")
        return

    print(f"Model      : {model_path}")
    print(f"Policy     : {policy}")
    print(f"Device     : {args.device}")

    if args.download_only:
        print("Download complete. Exiting (--download-only).")
        return

    if args.device == "NPU" and policy in NPU_LARGE_MODEL_WARNING:
        print(f"\nWARNING: {NPU_LARGE_MODEL_WARNING[policy]}\n")

    if policy not in SAMPLE_BUILDERS:
        raise ValueError(f"Unsupported policy '{policy}'. Supported: {list(SAMPLE_BUILDERS)}")

    # Build dummy sample
    builder = SAMPLE_BUILDERS[policy]
    sample = builder(args.task) if policy == "pi05" else builder()

    print(f"Warmup     : {args.warmup} iters")
    print(f"Measure    : {args.iters} iters")
    if policy == "pi05":
        print(f"Task       : '{args.task}'")
    print()

    model = InferenceModel(model_path, device=args.device)
    model.reset()

    benchmark = InferenceLatencyBenchmark(
        max_iters=args.iters,
        warmup_iters=args.warmup,
        max_duration=args.max_duration,
    )
    metrics = benchmark.run(model, inputs=repeat(sample))

    print("=== Results ===")
    print(f"Policy          : {policy}")
    print(f"Device          : {args.device}")
    print(f"Iterations      : {metrics['num_iters']}")
    print(f"Warmup avg      : {metrics['avg_warmup_iter_time']*1000:.2f} ms")
    print(f"Min latency     : {metrics['min_iter_time']*1000:.2f} ms")
    print(f"Max latency     : {metrics['max_iter_time']*1000:.2f} ms")
    print(f"Mean latency    : {metrics['mean_iter_time']*1000:.2f} ms")
    print(f"Median latency  : {metrics['median_iter_time']*1000:.2f} ms")
    print(f"Std dev         : {metrics['std_iter_time']*1000:.2f} ms")
    print(f"Throughput      : {1/metrics['mean_iter_time']:.1f} FPS")
    print()
    print("=== Raw JSON ===")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
