# AgroGuide

AgroGuide is an English-language smart farming web application built with Flask. It combines plant disease detection, crop tools, weather-based guidance, user history, administration, and a grounded farming chatbot in one responsive interface.

The disease scanner sends uploaded leaf images to a separately hosted prediction API and currently supports 38 plant-health classes. The chatbot uses local AgroGuide knowledge, external agricultural search results, and Google Gemini through a hybrid retrieval-augmented generation (RAG) workflow. External sources are displayed below the completed chatbot answer.

## Current features

- User registration, login, logout, email verification, and password recovery
- Plant leaf image upload, drag-and-drop, and camera capture
- Remote plant disease prediction through `MODEL_API_URL`
- 38 supported disease and healthy plant classes
- Disease descriptions, severity information, and treatment guidance
- Crop recommendation and crop suitability tools
- Cultivation, irrigation, fertilizer, and symptom-based farming guidance
- Open-Meteo weather forecasts and farming advice
- Hybrid RAG chatbot using local knowledge, external search, and Gemini
- Chatbot processing-status loader followed by the complete Markdown answer
- External chatbot sources displayed as links below the answer
- Searchable user activity and farming history
- Administration dashboard and disease-knowledge management
- Responsive interface with light and dark themes

## Supported disease detection classes

Total classes: **38**

1. `Apple___Apple_scab`
2. `Apple___Black_rot`
3. `Apple___Cedar_apple_rust`
4. `Apple___healthy`
5. `Blueberry___healthy`
6. `Cherry_(including_sour)___Powdery_mildew`
7. `Cherry_(including_sour)___healthy`
8. `Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot`
9. `Corn_(maize)___Common_rust_`
10. `Corn_(maize)___Northern_Leaf_Blight`
11. `Corn_(maize)___healthy`
12. `Grape___Black_rot`
13. `Grape___Esca_(Black_Measles)`
14. `Grape___Leaf_blight_(Isariopsis_Leaf_Spot)`
15. `Grape___healthy`
16. `Orange___Haunglongbing_(Citrus_greening)`
17. `Peach___Bacterial_spot`
18. `Peach___healthy`
19. `Pepper,_bell___Bacterial_spot`
20. `Pepper,_bell___healthy`
21. `Potato___Early_blight`
22. `Potato___Late_blight`
23. `Potato___healthy`
24. `Raspberry___healthy`
25. `Soybean___healthy`
26. `Squash___Powdery_mildew`
27. `Strawberry___Leaf_scorch`
28. `Strawberry___healthy`
29. `Tomato___Bacterial_spot`
30. `Tomato___Early_blight`
31. `Tomato___Late_blight`
32. `Tomato___Leaf_Mold`
33. `Tomato___Septoria_leaf_spot`
34. `Tomato___Spider_mites Two-spotted_spider_mite`
35. `Tomato___Target_Spot`
36. `Tomato___Tomato_Yellow_Leaf_Curl_Virus`
37. `Tomato___Tomato_mosaic_virus`
38. `Tomato___healthy`

Predictions should be treated as decision support rather than a replacement for laboratory testing or advice from a qualified agricultural professional.

## Technology stack

### Backend

- Python 3.11
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Werkzeug
- Gunicorn

### Data and integrations

- PostgreSQL with `psycopg2`
- AWS-hosted Flask disease-prediction API
- Google Gemini 2.5 Flash Lite, with Gemini 2.5 Flash as fallback
- Tavily Search for external RAG evidence
- Local AgroGuide farming knowledge
- Open-Meteo weather data
- Pillow for image validation and processing
- RapidFuzz for knowledge retrieval and matching

### Frontend

- Jinja templates
- Tailwind CSS
- Custom CSS
- Vanilla JavaScript
- Lucide icons
- Server-Sent Events for chatbot processing updates

### Deployment

- Vercel for the AgroGuide web application
- PostgreSQL database service
- AWS EC2 for the disease-prediction API

## Project structure

```text
AgroGuideApp/
├── api/                    # Vercel Flask entry point
├── app/
│   ├── data/               # Local farming and disease knowledge
│   ├── routes/             # Flask blueprints
│   ├── services/           # Chatbot, search, weather, crop, and model API services
│   ├── static/             # CSS, JavaScript, and static assets
│   ├── templates/          # Jinja templates
│   ├── uploads/            # Validated user image uploads
│   ├── __init__.py         # Flask application factory
│   └── models.py           # SQLAlchemy application models
├── config.py               # Environment-based configuration
├── requirements.txt        # Python dependencies
├── run.py                  # Local development entry point
├── schema.sql              # PostgreSQL schema
└── vercel.json             # Vercel deployment configuration
```

## Local setup

### 1. Create and activate a virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example configuration:

```powershell
Copy-Item .env.example .env
```

On macOS or Linux:

```bash
cp .env.example .env
```

Update at least the following values in `.env`:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session and token security |
| `DATABASE_URL` or `DB_*` | PostgreSQL connection configuration |
| `MODEL_API_URL` | Disease-prediction API `/predict` endpoint |
| `MODEL_API_TIMEOUT_SECONDS` | Prediction request timeout |
| `GEMINI_API_KEY` | Google Gemini API access |
| `GEMINI_MODEL` | Gemini model; defaults to `gemini-2.5-flash-lite` |
| `SEARCH_PROVIDER` | External RAG search provider; defaults to `tavily` |
| `SEARCH_API_KEY` | Tavily search API key |
| `ADMIN_EMAIL` | Initial administrator email when automatic initialization is enabled |
| `ADMIN_PASSWORD` | Initial administrator password when automatic initialization is enabled |
| `AUTO_INIT_DB` | Enables startup database initialization when set to `true` |
| `MAX_UPLOAD_MB` | Maximum accepted image upload size |

The application can start without a search API key, but the chatbot will rely on local knowledge and available fallback guidance. Disease scanning requires a valid `MODEL_API_URL`.

### 4. Prepare PostgreSQL

Create a PostgreSQL database and either:

- apply `schema.sql`, which is recommended for managed or production databases; or
- set `AUTO_INIT_DB=true` for initial local development setup.

After initialization, set `AUTO_INIT_DB=false` for normal production operation.

### 5. Run AgroGuide

```bash
python run.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Disease prediction configuration

The Flask web application does not load the disease-classification checkpoint locally. When a user submits a leaf image:

1. AgroGuide validates and stores the uploaded image.
2. The application sends it to `MODEL_API_URL` as multipart form data.
3. The remote prediction API returns the predicted class and confidence.
4. AgroGuide matches the class with its disease knowledge and displays the result.

Configure the endpoint as follows:

```env
MODEL_API_URL=http://your-model-api-host:5000/predict
MODEL_API_TIMEOUT_SECONDS=30
```

The prediction API must return a class name matching one of the 38 supported identifiers.

## Chatbot and hybrid RAG

The farming chatbot follows this high-level process:

1. Validate that the question is related to agriculture or AgroGuide.
2. Retrieve relevant local AgroGuide knowledge.
3. Retrieve external agricultural evidence when search is configured.
4. Build a grounded prompt from the conversation, user context, and evidence.
5. Generate the answer with Gemini.
6. Remove citation artifacts and display the complete Markdown response.
7. Show only valid external source links below the answer.

While processing, the interface reports its current stage instead of displaying a partial answer.

## Production notes

- Use a long, random `SECRET_KEY`.
- Use HTTPS for the web app, model API, and external services.
- Keep API keys and database credentials in deployment environment variables.
- Set `FLASK_DEBUG=false`.
- Apply `schema.sql` before production use.
- Keep `AUTO_INIT_DB=false` after database initialization.
- Restrict the model API so it is not unnecessarily exposed.
- Use a production WSGI server such as Gunicorn.

## Security

- Passwords are hashed with Werkzeug.
- Authentication is required for protected routes.
- Administrative routes require administrator access.
- Uploaded filenames are sanitized.
- Image extensions and upload sizes are validated.
- CSRF tokens protect state-changing browser requests.
- Password-reset and email-verification tokens expire.
- External chatbot sources are restricted to valid HTTP or HTTPS URLs.

## License

MIT
