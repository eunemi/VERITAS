"""When object detection is worth running, and on what.

Detection is not free and it is not always meaningful, so it is gated on the text
the image itself contains: an image whose recovered text says nothing about a
physical object gets no detector.

The gate matches against the fixed COCO vocabulary rather than any noun phrase,
and that is the important constraint. "The photo shows a tank" names an object
these weights cannot detect, and answering it with the ``truck`` the detector
*would* report is worse than reporting nothing at all. So a claim is only routed to
the detector when the thing it names is something the detector can actually be
right or wrong about.

Pure Python, and checked *before* the model loads — the point is to avoid the
several hundred megabytes and the first-use download, not to filter afterwards.
"""

from __future__ import annotations

from app.research.terms import fold, words

#: The 80 classes of the released YOLOv8 weights, in the order COCO defines them.
COCO_LABELS: frozenset[str] = frozenset(
    {
        "person",
        "bicycle",
        "car",
        "motorcycle",
        "airplane",
        "bus",
        "train",
        "truck",
        "boat",
        "traffic light",
        "fire hydrant",
        "stop sign",
        "parking meter",
        "bench",
        "bird",
        "cat",
        "dog",
        "horse",
        "sheep",
        "cow",
        "elephant",
        "bear",
        "zebra",
        "giraffe",
        "backpack",
        "umbrella",
        "handbag",
        "tie",
        "suitcase",
        "frisbee",
        "skis",
        "snowboard",
        "sports ball",
        "kite",
        "baseball bat",
        "baseball glove",
        "skateboard",
        "surfboard",
        "tennis racket",
        "bottle",
        "wine glass",
        "cup",
        "fork",
        "knife",
        "spoon",
        "bowl",
        "banana",
        "apple",
        "sandwich",
        "orange",
        "broccoli",
        "carrot",
        "hot dog",
        "pizza",
        "donut",
        "cake",
        "chair",
        "couch",
        "potted plant",
        "bed",
        "dining table",
        "toilet",
        "tv",
        "laptop",
        "mouse",
        "remote",
        "keyboard",
        "cell phone",
        "microwave",
        "oven",
        "toaster",
        "sink",
        "refrigerator",
        "book",
        "clock",
        "vase",
        "scissors",
        "teddy bear",
        "hair drier",
        "toothbrush",
    }
)

#: How people write about these objects, mapped to what the detector calls them.
#: Only where the two names denote the same thing — "crowd" is people, so it maps;
#: "tank" is not a truck, so it does not appear here at all.
SYNONYMS: dict[str, str] = {
    "crowd": "person",
    "people": "person",
    "protester": "person",
    "protesters": "person",
    "man": "person",
    "men": "person",
    "woman": "person",
    "women": "person",
    "child": "person",
    "children": "person",
    "police": "person",
    "officer": "person",
    "plane": "airplane",
    "aircraft": "airplane",
    "jet": "airplane",
    "lorry": "truck",
    "vehicle": "car",
    "automobile": "car",
    "taxi": "car",
    "sofa": "couch",
    "settee": "couch",
    "television": "tv",
    "telly": "tv",
    "monitor": "tv",
    "bike": "bicycle",
    "cycle": "bicycle",
    "motorbike": "motorcycle",
    "scooter": "motorcycle",
    "ship": "boat",
    "vessel": "boat",
    "ferry": "boat",
    "table": "dining table",
    "fridge": "refrigerator",
    "phone": "cell phone",
    "smartphone": "cell phone",
    "mobile": "cell phone",
}

_SUFFIXES = (("ies", "y"), ("ches", "ch"), ("shes", "sh"), ("ses", "s"), ("xes", "x"))


def _singular(word: str) -> str:
    """Crude English de-pluralisation. Enough for a vocabulary of 80 nouns."""
    for suffix, replacement in _SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix):
            return word[: -len(suffix)] + replacement
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _resolve(phrase: str) -> str | None:
    if phrase in COCO_LABELS:
        return phrase
    return SYNONYMS.get(phrase)


def wanted(text: str) -> frozenset[str]:
    """Detector labels the objects named in ``text`` correspond to.

    Two-word phrases are tried before single words, so "cell phone" resolves as
    itself rather than as "phone". Each phrase is tested both as written and with
    only its final token singularised: as written keeps the labels that are
    natively plural ("skis", "scissors"), and the singularised form catches
    "sports balls" and "cell phones".
    """
    found = set()
    tokens = words(fold(text))

    for size in (2, 1):
        for index in range(len(tokens) - size + 1):
            chunk = tokens[index : index + size]
            phrase = " ".join(chunk)
            reduced = " ".join([*chunk[:-1], _singular(chunk[-1])])
            label = _resolve(phrase) or _resolve(reduced)
            if label:
                found.add(label)

    return frozenset(found)
