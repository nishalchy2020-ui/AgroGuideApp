def register_blueprints(app):
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.detection import detection_bp
    from app.routes.weather import weather_bp
    from app.routes.chatbot import chatbot_bp
    from app.routes.admin import admin_bp
    from app.routes.crops import crops_bp
    from app.routes.irrigation import irrigation_bp
    from app.routes.fertilizer import fertilizer_bp
    from app.routes.pest import pest_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(detection_bp, url_prefix="/detection")
    app.register_blueprint(weather_bp, url_prefix="/weather")
    app.register_blueprint(chatbot_bp, url_prefix="/chatbot")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(crops_bp, url_prefix="/crops")
    app.register_blueprint(irrigation_bp, url_prefix="/irrigation")
    app.register_blueprint(fertilizer_bp, url_prefix="/fertilizer")
    app.register_blueprint(pest_bp, url_prefix="/pest")
