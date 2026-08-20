"""冻结视觉编码器封装（open_clip, checkpoint 固定）。"""

from __future__ import annotations

import numpy as np
import torch
import open_clip
from PIL import Image

from . import consts


class ClipEncoder:
    def __init__(self) -> None:
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            consts.CLIP_ARCH, pretrained=consts.CLIP_CKPT
        )
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(consts.CLIP_ARCH)
        self.logit_scale = float(self.model.logit_scale.exp().item())

    @torch.no_grad()
    def encode_images(self, images: list[np.ndarray], batch_size: int = 32) -> np.ndarray:
        """输入 HxWx3 uint8 列表 → L2 归一化特征 (N, dim)。"""
        feats = []
        for i in range(0, len(images), batch_size):
            batch = torch.stack([
                self.preprocess(Image.fromarray(img)) for img in images[i:i + batch_size]
            ])
            f = self.model.encode_image(batch)
            f = f / f.norm(dim=-1, keepdim=True)
            feats.append(f.cpu().numpy())
        return np.concatenate(feats, axis=0) if feats else np.zeros((0, 512))

    @torch.no_grad()
    def encode_texts(self, texts: list[str], batch_size: int = 256) -> np.ndarray:
        feats = []
        for i in range(0, len(texts), batch_size):
            tokens = self.tokenizer(texts[i:i + batch_size])
            f = self.model.encode_text(tokens)
            f = f / f.norm(dim=-1, keepdim=True)
            feats.append(f.cpu().numpy())
        return np.concatenate(feats, axis=0) if feats else np.zeros((0, 512))
