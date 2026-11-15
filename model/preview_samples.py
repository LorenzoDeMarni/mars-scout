"""Export a few AI4Mars samples as viewable PNGs: photo next to its colored label mask.

Usage: python model/preview_samples.py [parquet_file] [count]
Writes to data/preview/.
"""
import io
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "data/ai4mars/data/test_min3-00000-of-00001.parquet"
OUT = ROOT / "data/preview"

# class id -> (name, color)
CLASSES = {
    0: ("soil", (166, 118, 74)),
    1: ("bedrock", (70, 130, 220)),
    2: ("sand", (240, 200, 60)),
    3: ("big rock", (220, 50, 50)),
    255: ("no label", (0, 0, 0)),
}


def decode(cell):
    return Image.open(io.BytesIO(cell["bytes"])) if cell and cell.get("bytes") else None


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    OUT.mkdir(parents=True, exist_ok=True)

    pf = pq.ParquetFile(path)
    print(f"{path.name}: {pf.metadata.num_rows} rows, columns {pf.schema_arrow.names}")
    rows = next(pf.iter_batches(batch_size=count)).to_pylist()

    for i, row in enumerate(rows):
        photo = decode(row["image"]).convert("RGB")
        label = decode(row["label_mask"])
        if label is None:
            print(f"sample {i}: no label")
            continue
        mask = np.array(label)
        if mask.ndim == 3:
            mask = mask[..., 0]
        values, counts = np.unique(mask, return_counts=True)
        share = {CLASSES.get(v, (str(v),))[0]: f"{c / mask.size:.0%}" for v, c in zip(values, counts)}
        print(f"sample {i}: photo {photo.size} {decode(row['image']).mode}, mask values {share}")

        color = np.zeros((*mask.shape, 3), dtype=np.uint8)
        for value, (_, rgb) in CLASSES.items():
            color[mask == value] = rgb
        side = Image.new("RGB", (photo.width * 2, photo.height))
        side.paste(photo, (0, 0))
        side.paste(Image.fromarray(color).resize(photo.size, Image.NEAREST), (photo.width, 0))
        side.save(OUT / f"sample_{i:02d}.png")

    print(f"wrote {len(rows)} previews to {OUT}")


if __name__ == "__main__":
    main()
