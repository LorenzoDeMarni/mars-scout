"""Score the trained model on the expert-labeled AI4Mars test sets.

Usage: uv run python model/evaluate.py
Writes checkpoints/test_results.json. Only labeled pixels are scored.
"""
import json

import torch
from torch.utils.data import DataLoader

from common import CHECKPOINTS, Shards, build_model
from train import evaluate


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = build_model().to(device)
    model.load_state_dict(torch.load(CHECKPOINTS / "terrain.pt", map_location=device))
    results = {}
    for split in ["test_min1", "test_min2", "test_min3"]:
        report = evaluate(model, DataLoader(Shards(split), batch_size=8, num_workers=4), device)
        results[split] = report
        ious = ", ".join(f"{c} {v:.3f}" for c, v in report["iou"].items())
        print(f"{split}: pixel accuracy {report['pixel_accuracy']:.3f}, mean IoU {report['mean_iou']:.3f} ({ious})")
    (CHECKPOINTS / "test_results.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
