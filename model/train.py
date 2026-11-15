"""Fine-tune the terrain segmentation model on AI4Mars.

Usage: uv run python model/train.py [--epochs 8] [--batch 8] [--limit N]
Saves checkpoints/terrain.pt (best validation mean IoU) and checkpoints/train_log.json.
--limit N trains on only N images, for a quick check that everything runs.
"""
import argparse
import json
import time

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Subset

from common import CHECKPOINTS, IGNORE, Confusion, Shards, build_model, to_input


def evaluate(model, loader, device):
    model.eval()
    conf = Confusion()
    with torch.no_grad(), torch.autocast("cuda", enabled=device == "cuda"):
        for img, mask in loader:
            pred = model(to_input(img.to(device))).argmax(1)
            conf.add(pred, mask.to(device))
    return conf.report()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(0)

    # Hold out 5% of the crowd-labeled images for validation. The expert test set
    # is only touched by evaluate.py.
    n = len(Shards("train"))
    order = torch.randperm(n, generator=torch.Generator().manual_seed(0)).tolist()
    n_val = n // 20
    val_idx, train_idx = order[:n_val], order[n_val:]
    if args.limit:
        train_idx, val_idx = train_idx[: args.limit], val_idx[: max(args.limit // 4, 16)]
    train = DataLoader(Subset(Shards("train", augment=True), train_idx), batch_size=args.batch,
                       shuffle=True, num_workers=6, drop_last=True, persistent_workers=True)
    val = DataLoader(Subset(Shards("train"), val_idx), batch_size=args.batch, num_workers=4)
    print(f"{len(train_idx)} training images, {len(val_idx)} validation images, device {device}")

    model = build_model().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=args.epochs * len(train))
    scaler = torch.amp.GradScaler(enabled=device == "cuda")

    CHECKPOINTS.mkdir(exist_ok=True)
    log, best = [], -1.0
    for epoch in range(args.epochs):
        model.train()
        start, running = time.time(), 0.0
        for step, (img, mask) in enumerate(train):
            img, mask = img.to(device), mask.to(device)
            with torch.autocast("cuda", enabled=device == "cuda"):
                # unlabeled pixels (255) contribute nothing to the loss
                loss = F.cross_entropy(model(to_input(img)), mask, ignore_index=IGNORE)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            running += loss.item()
            if step % 100 == 0:
                print(f"epoch {epoch + 1} step {step}/{len(train)} loss {loss.item():.3f}", flush=True)
        report = evaluate(model, val, device)
        entry = {"epoch": epoch + 1, "train_loss": running / len(train),
                 "minutes": (time.time() - start) / 60, **report}
        log.append(entry)
        print(f"epoch {epoch + 1}: loss {entry['train_loss']:.3f}, val accuracy "
              f"{report['pixel_accuracy']:.3f}, val mean IoU {report['mean_iou']:.3f}, "
              f"{entry['minutes']:.1f} min", flush=True)
        if report["mean_iou"] > best:
            best = report["mean_iou"]
            torch.save(model.state_dict(), CHECKPOINTS / "terrain.pt")
        (CHECKPOINTS / "train_log.json").write_text(json.dumps(log, indent=2))
    print(f"done, best val mean IoU {best:.3f}")


if __name__ == "__main__":
    main()
