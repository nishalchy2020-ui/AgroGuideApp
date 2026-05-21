import json
import logging
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import models, transforms

logger = logging.getLogger(__name__)

_model = None
_class_names = None
_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

TRANSFORM = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ]
)


def _load_class_indices(path: Path):
    """Load class names in model output order (index 0 .. N-1).

    Supports both common JSON layouts:
      - index -> name:  {"0": "Tomato_healthy", "1": "..."}
      - name -> index:  {"Tomato_healthy": 0, "Apple___Apple_scab": 1, ...}
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return list(data)

    if not isinstance(data, dict) or not data:
        raise ValueError("class_indices.json must be a non-empty dict or list")

    sample_key = next(iter(data))
    try:
        int(sample_key)
        keys_are_indices = True
    except (ValueError, TypeError):
        keys_are_indices = False

    if keys_are_indices:
        sorted_items = sorted(data.items(), key=lambda x: int(x[0]))
        return [str(name) for _, name in sorted_items]

    sorted_items = sorted(data.items(), key=lambda x: int(x[1]))
    return [str(name) for name, _ in sorted_items]


def _align_class_names(names, num_classes: int):
    """Pad or trim labels so length matches the checkpoint classifier size."""
    names = list(names)
    if len(names) == num_classes:
        return names
    if len(names) < num_classes:
        logger.warning(
            "class_indices.json has %d labels but the model has %d classes. "
            "Missing indices will use generic names (class_N).",
            len(names),
            num_classes,
        )
        for i in range(len(names), num_classes):
            names.append(f"class_{i}")
        return names
    logger.warning(
        "class_indices.json has %d labels but the model has %d classes. Trimming extra labels.",
        len(names),
        num_classes,
    )
    return names[:num_classes]


def _extract_state_dict(checkpoint_path: Path):
    try:
        checkpoint = torch.load(
            checkpoint_path, map_location=_device, weights_only=False
        )
    except TypeError:
        checkpoint = torch.load(checkpoint_path, map_location=_device)
    if isinstance(checkpoint, dict):
        for key in ("model_state_dict", "state_dict", "model"):
            if key in checkpoint and isinstance(checkpoint[key], dict):
                return checkpoint[key]
        if any(k.endswith(".weight") or k.endswith(".bias") for k in checkpoint):
            return checkpoint
    raise ValueError(f"Unrecognized checkpoint format: {checkpoint_path}")


def _infer_num_classes(state_dict) -> int:
    """Read output size from the final classifier Linear layer in the checkpoint."""
    candidates = []
    for key, tensor in state_dict.items():
        if not hasattr(tensor, "shape") or len(tensor.shape) != 2:
            continue
        key_lower = key.lower()
        if "classifier" in key_lower and key.endswith(".weight"):
            # Linear weight shape is [out_features, in_features]
            candidates.append((key, int(tensor.shape[0])))

    if not candidates:
        raise ValueError(
            "Could not infer number of classes from checkpoint. "
            "Expected a classifier Linear weight (e.g. classifier.1.weight)."
        )

    # Prefer the last classifier layer (highest index in name)
    def sort_key(item):
        key = item[0]
        parts = key.split(".")
        nums = [int(p) for p in parts if p.isdigit()]
        return (key.count("classifier"), nums[-1] if nums else 0)

    candidates.sort(key=sort_key)
    key, num_classes = candidates[-1]
    logger.info("Inferred %d classes from checkpoint key: %s", num_classes, key)
    return num_classes


def _build_model(num_classes: int):
    model = models.mobilenet_v2(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier[1] = torch.nn.Linear(in_features, num_classes)
    return model


def _load_state_dict(model, state_dict):
    model_state = model.state_dict()
    filtered = {}
    for key, value in state_dict.items():
        target_key = key
        if target_key not in model_state and key.startswith("module."):
            target_key = key[7:]
        if target_key in model_state and model_state[target_key].shape == value.shape:
            filtered[target_key] = value
    missing, unexpected = model.load_state_dict(filtered, strict=False)
    if missing:
        logger.debug("Checkpoint keys not loaded: %s", missing[:5])
    if unexpected:
        logger.debug("Unexpected checkpoint keys: %s", unexpected[:5])


def load_model(checkpoint_path=None, class_indices_path=None):
    global _model, _class_names

    from flask import current_app

    checkpoint_path = Path(
        checkpoint_path or current_app.config["MODEL_CHECKPOINT"]
    )
    class_indices_path = Path(
        class_indices_path or current_app.config["CLASS_INDICES"]
    )

    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"Model checkpoint not found: {checkpoint_path}. "
            "Place plant_disease_checkpoint.pth in app/ml_models/"
        )
    if not class_indices_path.exists():
        raise FileNotFoundError(
            f"Class indices not found: {class_indices_path}. "
            "Place class_indices.json in app/ml_models/"
        )

    state_dict = _extract_state_dict(checkpoint_path)
    num_classes = _infer_num_classes(state_dict)

    labels = _load_class_indices(class_indices_path)
    _class_names = _align_class_names(labels, num_classes)

    _model = _build_model(num_classes)
    _load_state_dict(_model, state_dict)
    _model.to(_device)
    _model.eval()
    return _model


def is_model_ready():
    from flask import current_app

    return (
        Path(current_app.config["MODEL_CHECKPOINT"]).exists()
        and Path(current_app.config["CLASS_INDICES"]).exists()
    )


def predict(image_path):
    global _model, _class_names

    if _model is None or _class_names is None:
        load_model()

    image = Image.open(image_path).convert("RGB")
    tensor = TRANSFORM(image).unsqueeze(0).to(_device)

    with torch.no_grad():
        outputs = _model(tensor)
        probs = F.softmax(outputs, dim=1)[0]
        confidence, idx = torch.max(probs, 0)

    idx = int(idx)
    if idx >= len(_class_names):
        class_name = f"class_{idx}"
    else:
        class_name = _class_names[idx]

    return {
        "class_name": class_name,
        "confidence": float(confidence.item()),
        "confidence_percent": round(float(confidence.item()) * 100, 2),
    }
