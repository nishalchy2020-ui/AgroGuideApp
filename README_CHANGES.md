# AgroGuide Change Summary

This file documents the production and feature changes made after the PostgreSQL migration, without changing the original `README.md`.

## PostgreSQL and Vercel

- Production database usage was aligned with PostgreSQL instead of SQLite.
- PostgreSQL configuration supports either `DATABASE_URL` or individual variables: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.
- `AUTO_INIT_DB` remains `false` for production after applying the PostgreSQL schema manually.
- `schema.sql` is ignored in git so local schema files are not committed accidentally.
- The Vercel Python entrypoint now exposes top-level `app` and `application`.
- Added Vercel diagnostic routes:
  - `/_vercel_probe`
  - `/_vercel_db_probe`
- Removed unsupported `connect_timeout` engine args for the deployed database driver.
- Added `DATABASE_URL` sanitizing to remove unsupported `connect_timeout` query parameters while preserving other query parameters.

## Performance

- Vercel functions are configured for the Stockholm region, `arn1`, to reduce latency to the AWS `eu-north-1` PostgreSQL database.
- Static files under `/static/*` are served through Vercel static/CDN instead of the Python function.
- Runtime Tailwind CDN compilation was replaced with compiled local CSS.
- Static assets now use cache headers for faster repeat navigation.
- Dashboard count queries were combined to reduce database round trips.
- Added `Server-Timing` and `X-Response-Time-ms` response headers to help diagnose slow pages in browser devtools.

## Disease Detection

- Rewrote the Disease Detection “How it works” copy to explain that leaf images are sent to the trained AI model, which returns the predicted class and confidence.
- Added low-confidence guidance: if confidence is below 60%, users should treat the result as uncertain and consult an agriculture expert before treatment.
- Added a result-page warning when prediction confidence is below 60%.
- Added a “View all supported detections” button from the Disease Detection page.
- Added a dedicated supported detections page at `/detection/supported-detections`.
- The supported detections page lists each supported plant/disease class with:
  - readable disease name
  - short description
  - raw model class key
- The supported detections layout was adjusted to avoid overlapping cards and long class-key overflow on mobile and desktop.

## Files Commonly Affected

- `api/index.py`
- `app/__init__.py`
- `app/routes/detection.py`
- `app/routes/main.py`
- `app/templates/base.html`
- `app/templates/detection/index.html`
- `app/templates/detection/result.html`
- `app/templates/detection/supported.html`
- `app/static/css/tailwind.css`
- `app/static/css/tailwind.input.css`
- `app/static/js/theme.js`
- `config.py`
- `tailwind.config.js`
- `vercel.json`
