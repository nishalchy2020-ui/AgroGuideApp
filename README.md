# AgroGuide
# AgroGuide

English-only modern SaaS-style AI smart farming dashboard built with Flask, SQLite, Tailwind CSS, vanilla JavaScript, and PyTorch.

## Features

- User authentication (register, login, logout, password hashing)
- Plant disease detection (upload, drag-and-drop, camera capture)
- PyTorch MobileNetV2 integration
- Disease knowledge base (23+ dataset classes)
- **Crop recommendation** — local pretrained crop ranking by soil, season, water, temperature
- **Offline crop model** — bundled centroid model, no Gemini quota required
- **Crop suitability checker** — scored analysis with suggestions
- **Cultivation guides** — timeline UI per crop
- **Irrigation advice** — growth stage and rainfall aware
- **Fertilizer guidance** — NPK/pH optional inputs
- **Symptom-based pest help** — links to AI leaf scan
- Open-Meteo weather with farming advice and disease risk
- **Google Gemini** farming assistant (replaces rule-based chat)
- **Unified history** — search, filter by module, date, delete
- Admin panel with analytics and knowledge management
- Glassmorphism UI, Lucide icons, dark/light mode

## Project structure

```
agroguide/
├── app/
│   ├── routes/          # Blueprints
│   ├── services/        # Model, weather, chatbot, knowledge
│   ├── templates/       # Jinja2 + Tailwind
│   ├── static/          # CSS & JS
│   ├── uploads/         # User scan images
│   ├── ml_models/       # Paste your model here
│   └── data/            # Disease knowledge JSON
├── config.py
├── run.py
└── requirements.txt
```

## Setup

### 1. Virtual environment

```bash
cd agroguide
python -m venv venv
```

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment variables

```bash
copy .env.example .env
```

Copy the example environment file and edit values:

```bash
copy .env.example .env
```

Required / recommended variables (loaded via `python-dotenv` in `config.py`):

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask session secret (required in production) |
| `GEMINI_API_KEY` | Google AI Studio key for AI Assistant |
| `GEMINI_MODEL` | Default `gemini-2.0-flash-lite` for the free tier; fallback `gemini-2.0-flash` |
| `SEARCH_PROVIDER` | Internet search provider for hybrid chatbot, default `tavily` |
| `SEARCH_API_KEY` | Search API key for Tavily, SerpAPI, Brave Search, or Google Custom Search |
| `DATABASE_URL` | PostgreSQL connection URL; if unset, the app builds one from `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` |
| `AUTO_INIT_DB` | Creates database tables at startup when true; keep false in production after applying `schema.sql` |
| `PORT` | Server port (default `5000`) |

The app starts without `SEARCH_API_KEY`; the chatbot uses local AgroGuide knowledge and fallback farming guidance instead of crashing.

### 4. Add your trained model

Copy into `app/ml_models/`:

| File | Required |
|------|----------|
| `plant_disease_checkpoint.pth` | Yes |
| `class_indices.json` | Yes |

See `app/ml_models/README.md` and `class_indices.json.example` for format.

### 5. Run the application

```bash
python run.py
```

Open http://127.0.0.1:5000

## Default admin account

| Field | Value |
|-------|-------|
| Email | `admin@agroguide.com` |
| Password | `Admin@12345` |

Override via `.env`: `ADMIN_EMAIL`, `ADMIN_PASSWORD`.

On login, check **Admin login** to go directly to the admin panel.

## Model integration

`app/services/model_service.py`:

- Loads `torchvision.models.mobilenet_v2`
- Rebuilds classifier for `num_classes` from `class_indices.json`
- Preprocess: Resize 224×224 → ToTensor → ImageNet normalize
- Returns class name and confidence

`app/services/crop_model.py`:

- Loads the bundled `app/data/crop_model.json` centroid model
- Scores soil, season, water, temperature, rainfall, and humidity locally
- Returns the same recommendation format used by the crop route
- Falls back to rule scoring if the local model cannot load

## Database tables

- `users` — accounts and admin flag
- `scan_results` — disease predictions
- `weather_searches` — location weather history
- `chatbot_messages` — chat history
- `disease_knowledge` — editable knowledge base
- `admin_logs` — admin actions

SQLite file: `agroguide.db` (project root).

## Security notes

- Werkzeug password hashing
- Secure filename uploads
- Image type validation (PNG, JPG, JPEG, WEBP)
- 8MB default upload limit (`MAX_UPLOAD_MB`)
- Login required for dashboard routes
- Admin decorator for admin panel

## Tech stack

- Flask, Flask-SQLAlchemy, Flask-Login
- PyTorch, torchvision, Pillow
- Open-Meteo API (no API key)
- Tailwind CSS (CDN), vanilla JavaScript

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

## License

MIT — use freely for learning and deployment.



