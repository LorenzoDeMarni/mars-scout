"""Shared pieces for the terrain model: paths, classes, dataset, model, metrics."""
from pathlib import Path

import numpy as np
import segmentation_models_pytorch as smp
import torch
from torch.utils.data import Dataset

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/ai4mars/data"
PREPARED = ROOT / "data/prepared"
CHECKPOINTS = ROOT / "checkpoints"

SIZE = 512
CLASSES = ["soil", "bedrock", "sand", "big rock"]
IGNORE = 255


def build_model():
    # U-Net with an ImageNet-pretrained ResNet-34 encoder. Photos are greyscale,
    # repeated to 3 channels so the pretrained first layer can be reused.
    return smp.Unet("resnet34", encoder_weights="imagenet", in_channels=3, classes=len(CLASSES))


def to_input(grey):
    """uint8 greyscale tensor (..., H, W) -> float tensor (..., 3, H, W) in model range."""
    x = grey.float().div(255).sub(0.5).div(0.25)
    return x.unsqueeze(-3).expand(*x.shape[:-2], 3, *x.shape[-2:])


class Shards(Dataset):
    """Reads the arrays written by prepare_data.py for one split prefix (e.g. 'train')."""

    def __init__(self, prefix, augment=False):
        files = sorted(PREPARED.glob(f"{prefix}*_img.npy"))
        if not files:
            raise FileNotFoundError(f"no prepared data for '{prefix}'; run model/prepare_data.py")
        self.images = [np.load(f, mmap_mode="r") for f in files]
        self.masks = [np.load(str(f).replace("_img.npy", "_mask.npy"), mmap_mode="r") for f in files]
        self.index = [(s, i) for s, arr in enumerate(self.images) for i in range(len(arr))]
        self.augment = augment

    def __len__(self):
        return len(self.index)

    def __getitem__(self, n):
        s, i = self.index[n]
        img = np.array(self.images[s][i])
        mask = np.array(self.masks[s][i])
        if self.augment:
            if np.random.rand() < 0.5:
                img, mask = img[:, ::-1], mask[:, ::-1]
            gain = np.random.uniform(0.7, 1.3)
            img = np.clip(img.astype(np.float32) * gain, 0, 255).astype(np.uint8)
        return torch.from_numpy(np.ascontiguousarray(img)), torch.from_numpy(np.ascontiguousarray(mask)).long()


class Confusion:
    """Confusion matrix over labeled pixels only."""

    def __init__(self):
        self.m = torch.zeros(len(CLASSES), len(CLASSES), dtype=torch.long)

    def add(self, pred, target):
        keep = target != IGNORE
        k = len(CLASSES)
        self.m += torch.bincount(target[keep] * k + pred[keep], minlength=k * k).reshape(k, k).cpu()

    def report(self):
        m = self.m.double()
        tp = m.diag()
        iou = tp / (m.sum(0) + m.sum(1) - tp).clamp(min=1)
        return {
            "pixel_accuracy": (tp.sum() / m.sum().clamp(min=1)).item(),
            "mean_iou": iou.mean().item(),
            "iou": {c: iou[i].item() for i, c in enumerate(CLASSES)},
            "labeled_pixels": {c: int(m[i].sum()) for i, c in enumerate(CLASSES)},
        }
