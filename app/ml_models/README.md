# AgroGuide ML Models

Place your trained model files in this directory:

| File | Description |
|------|-------------|
| `plant_disease_checkpoint.pth` | PyTorch state dict or full checkpoint for MobileNetV2 classifier |
| `class_indices.json` | JSON mapping index → class name (e.g. `{"0": "Tomato_healthy", "1": "..."}`) |

## Expected checkpoint format

The app loads **MobileNetV2** from torchvision and sets `num_classes` from the **checkpoint** (classifier layer shape). Labels come from `class_indices.json` and must cover every index `0 .. num_classes-1`. If your JSON has fewer names than the model, generic `class_N` labels are used for the rest.

Supported checkpoint keys (first match wins):
- Full model `state_dict`
- Nested `model_state_dict` / `state_dict`

## Example class_indices.json

Either format works:

**Index → class name:**
```json
{
  "0": "Apple___Apple_scab",
  "1": "Tomato_healthy"
}
```

**Class name → index** (common PyTorch training export):
```json
{
  "Apple___Apple_scab": 0,
  "Tomato_healthy": 1
}
```

After adding files, restart the Flask app. Predictions work once both files are present.
