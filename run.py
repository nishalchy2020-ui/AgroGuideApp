"""
AgroGuide entry point. Loads .env before importing the application factory.
"""
from dotenv import load_dotenv

load_dotenv()

from config import getenv_int, getenv_bool, get_config
from app import create_app

app = create_app(get_config())

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=getenv_int("PORT", 5000),
        debug=getenv_bool("FLASK_DEBUG", default=True),
    )
