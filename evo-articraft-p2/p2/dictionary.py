"""Cross-object part dictionary + whole-object 3-view shape classification.

Both reuse the exact GF1/GF2 recipe already in runner.py (encode a fixed
candidate pool once, encode the query image, softmax the row) -- only the
candidate pool changes: instead of "this object's own siblings" (GF2) or
"the other 19 objects in this run" (GF1), the pool here is a *category*
vocabulary that does not depend on which object is being measured.

CATEGORY_TEXTS has 19 entries. 17 of them are the top head-nouns of
`expected_parts[].name` counted across A1-6 for yiyun/data/contracts-300/
(98 parsed contracts, 2026-08-20 snapshot; plural/singular and near-synonyms
merged by hand -- see the frequency table in the project chat log). The other
2 ("hinge/bearing", "axle") did NOT rank in that frequency scan; they were
added by hand because the original request named "bearing" explicitly as an
example category. Some other high-frequency words from the scan (carriage,
head, barrel, plate, flap) were deliberately left out as not visually
distinct enough from an existing entry. Swap this for image-averaged
prototypes later (see `build_image_prototypes`) once part renders exist for
enough real objects; text-only is a v1 placeholder, not a trained embedding
index.

v1.1 revision (after running all 20 cases and inspecting every part's
dictionary_best_category by hand): "base" and "hinge/bearing" were acting as
attractors -- 11 and 9 unrelated parts respectively (control panels, drawers,
keypads, mount arms, phalanx-chain links...) were being pulled into those two
categories, not because they resemble a base/hinge but because the original
descriptions were vague enough to match almost any boxy or elongated shape.
Rewrote both to name a discriminating trait (aspect ratio, size relative to
the object) instead of just naming the category. Added "key/switch" -- "keys"
scored 4 in the frequency scan (dropped in v1 as "not distinct enough"), but
rec_cash_register's 16 keys and rec_all_in_one_printer's control-panel keys
were all being misclassified as "frame", which is the concrete failure this
category exists to catch. This is still a best-effort wording fix, not a
verified one -- CLIP's zero-shot match to a flat, untextured gray render is a
weak signal regardless of how the sentence is worded; the real fix is still
image-averaged prototypes (`build_image_prototypes`).
"""

from __future__ import annotations

import numpy as np

# category -> (frequency in contracts-300 head-noun scan, short shape description)
CATEGORY_TEXTS: dict[str, str] = {
    "housing/body": "a large enclosing housing or body shell",
    # v1: "a flat wide base or stand plate" pulled in 11 unrelated parts
    # (control panels, drawers, keypads...) that are merely boxy or flat.
    # Narrowed to the trait that actually distinguishes a base: it is the
    # widest, lowest part, and other parts sit on top of it.
    "base": "the widest, lowest support platform that other parts rest on top of",
    "arm": "an elongated mechanical arm or lever",
    "lid": "a flat lid or cover that closes an opening",
    "door/panel": "a flat rectangular door or panel",
    "ring": "a thin circular ring or hoop",
    "dial": "a round rotary dial or selector knob",
    "button/knob": "a small round raised button or knob, circular from the front",
    # new: "keys" scored 4 in the frequency scan but was dropped in v1;
    # re-added after seeing cash-register/printer keys misclassified as
    # "frame" because they don't match round button/knob either.
    "key/switch": "a small flat rectangular key or switch, wider than it is tall, arranged in a row or grid with others like it",
    "jaw": "a clamping jaw with a flat gripping face",
    "bracket": "a flat L-shaped or U-shaped mounting bracket",
    "wheel": "a round wheel, caster, or roller, seen face-on showing its circular tread",
    "drawer": "a rectangular open-top drawer or sliding tray",
    "handle": "a long thin curved handle or grip bar",
    "post/tube": "a long straight post, tube, or column",
    "frame": "a rectangular structural frame surrounding an opening",
    "cap/cover": "a small cap or cover that fits over an end",
    # v1: "a small cylindrical hinge, bearing, or pivot joint" pulled in 9
    # unrelated parts (mount arms, phalanx-chain links...). Narrowed to
    # emphasize it is much smaller than the parts it connects, not just
    # "cylindrical" (arms and links are cylindrical too).
    "hinge/bearing": "a small cylindrical pin or pivot connector, noticeably smaller than the two parts it joins",
    "axle": "a thin straight shaft or axle",
}

# coarse whole-object category vocabulary for the 3-view shape classifier.
# Not the same list as CATEGORY_TEXTS (that one is part-level); this one is
# object-level, matching the "10 different classes" the 3-view check runs on.
SHAPE_CATEGORY_TEXTS: dict[str, str] = {
    "cabinet/storage": "a household cabinet or storage furniture with doors or drawers",
    "fan": "an electric desk or floor fan with blades",
    "chair": "an office or task chair",
    "lamp/light": "a table, floor, or floodlight lamp",
    "door/hatch": "a hinged door, hatch, gate, or lid",
    "machine housing": "an industrial machine housing or power tool",
    "wind/water turbine": "a wind turbine or waterwheel",
    "hvac": "an air conditioning or ventilation unit",
    "cutting tool": "a paper cutter, saw, or blade tool",
    "wheeled vehicle": "a vehicle or wheeled cart",
    "linkage/chain": "a multi-joint robotic arm or linkage chain",
    "handheld device": "a handheld electronic device such as a phone or glasses",
}


def _softmax_self_match(image_feats: np.ndarray, text_feats: np.ndarray, logit_scale: float
                         ) -> tuple[np.ndarray, np.ndarray]:
    """Row-normalized probs and raw sims for an MxK image-vs-text comparison."""
    sims = image_feats @ text_feats.T
    logits = logit_scale * sims
    probs = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs = probs / probs.sum(axis=1, keepdims=True)
    return probs, sims


def score_part_against_dictionary(part_image_feat: np.ndarray, enc, categories: dict[str, str] | None = None
                                   ) -> dict:
    """One part's averaged image feature vs. the fixed cross-object category pool."""
    categories = categories or CATEGORY_TEXTS
    names = list(categories)
    text_feats = enc.encode_texts([categories[n] for n in names])
    probs, sims = _softmax_self_match(part_image_feat[None, :], text_feats, enc.logit_scale)
    order = np.argsort(-sims[0])
    best_prob = float(probs[0, int(order[0])])
    # Unlike GF2's sibling pool (size varies per object), the dictionary's
    # candidate pool is the same fixed size for every part, so the chance
    # baseline is constant: 1/len(categories). Reported anyway, on the same
    # "how many times better than a blind guess" scale as GF2's vs_chance,
    # so the two numbers can be read side by side.
    chance = 1.0 / len(names)
    return {
        "dictionary_top3": [
            (names[i], float(sims[0, i]), float(probs[0, i])) for i in order[:3]
        ],
        "dictionary_best_category": names[int(order[0])],
        "dictionary_best_prob": best_prob,
        "dictionary_best_prob_vs_chance": best_prob / chance,
    }


def classify_shape_from_views(view_feats: np.ndarray, enc) -> dict:
    """Average N view embeddings, zero-shot-classify against SHAPE_CATEGORY_TEXTS."""
    m = view_feats.mean(axis=0)
    m = m / (np.linalg.norm(m) + 1e-12)
    names = list(SHAPE_CATEGORY_TEXTS)
    text_feats = enc.encode_texts([SHAPE_CATEGORY_TEXTS[n] for n in names])
    probs, sims = _softmax_self_match(m[None, :], text_feats, enc.logit_scale)
    order = np.argsort(-sims[0])
    return {
        "shape_top3": [
            (names[i], float(sims[0, i]), float(probs[0, i])) for i in order[:3]
        ],
        "shape_best_guess": names[int(order[0])],
        "shape_best_prob": float(probs[0, int(order[0])]),
    }


def build_image_prototypes(category_to_images: dict[str, list[np.ndarray]], enc) -> dict[str, np.ndarray]:
    """v2 upgrade path: average real part-render embeddings per category instead
    of a single hand-written sentence. Not wired into runner.py yet -- needs a
    real corpus of confidently-labeled part renders across many objects first.
    """
    out = {}
    for name, images in category_to_images.items():
        if not images:
            continue
        feats = enc.encode_images(images)
        m = feats.mean(axis=0)
        out[name] = m / (np.linalg.norm(m) + 1e-12)
    return out
