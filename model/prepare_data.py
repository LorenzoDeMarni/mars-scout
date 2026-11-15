"""Unpack the AI4Mars Parquet files into 512x512 arrays that train quickly.

Run once: uv run python model/prepare_data.py
Writes data/prepared/<shard>_img.npy and <shard>_mask.npy (about 9 GB in total).
Training images without labels are skipped. Rover hardware in training images becomes class 4.
"""
import io
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pyarrow.parquet as pq
from PIL import Image

from common import PREPARED, RAW, ROVER, SIZE


def convert(path):
    name = path.name.split("-of-")[0]  # e.g. train-00003 or test_min1-00000
    out_img = PREPARED / f"{name}_img.npy"
    if out_img.exists():
        return name, len(np.load(out_img, mmap_mode="r"))
    images, masks = [], []
    pf = pq.ParquetFile(path)
    for batch in pf.iter_batches(batch_size=32, columns=["image", "label_mask", "rover_mask", "has_labels"]):
        for row in batch.to_pylist():
            if not row["has_labels"] or not row["label_mask"]:
                continue
            img = Image.open(io.BytesIO(row["image"]["bytes"])).convert("L")
            mask = Image.open(io.BytesIO(row["label_mask"]["bytes"]))
            if mask.mode != "L":
                mask = mask.split()[0]
            images.append(np.asarray(img.resize((SIZE, SIZE), Image.BILINEAR)))
            # nearest keeps class ids intact (no blending between classes)
            mask = np.array(mask.resize((SIZE, SIZE), Image.NEAREST))
            # Training images only: mark rover hardware as its own class so the model learns
            # to recognise it. The expert test labels are left exactly as published.
            if name.startswith("train") and row["rover_mask"]:
                rover = Image.open(io.BytesIO(row["rover_mask"]["bytes"]))
                if rover.mode != "L":
                    rover = rover.split()[0]
                mask[np.asarray(rover.resize((SIZE, SIZE), Image.NEAREST)) > 0] = ROVER
            masks.append(mask)
    np.save(PREPARED / f"{name}_mask.npy", np.stack(masks))
    np.save(out_img, np.stack(images))  # written last: its presence marks the shard as done
    return name, len(images)


def main():
    PREPARED.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW.glob("*.parquet"))
    with ProcessPoolExecutor(max_workers=6) as pool:
        for name, n in pool.map(convert, files):
            print(f"{name}: {n} images")


if __name__ == "__main__":
    main()
