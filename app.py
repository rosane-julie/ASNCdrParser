import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure upload settings
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///cdr_parser.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize the app with the extension
db.init_app(app)

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

with app.app_context():
    # Import models and routes
    import models  # noqa: F401
    import routes  # noqa: F401

    # Create all database tables
    db.create_all()

    # Ensure new columns exist for older databases
    from sqlalchemy import inspect

    inspector = inspect(db.engine)
    columns = [col["name"] for col in inspector.get_columns("cdr_file")]
    if "parse_offset" not in columns:
        db.session.execute(
            db.text("ALTER TABLE cdr_file ADD COLUMN parse_offset INTEGER DEFAULT 0")
        )
        db.session.commit()
    if "spec_path" not in columns:
        db.session.execute(
            db.text("ALTER TABLE cdr_file ADD COLUMN spec_path VARCHAR(255)")
        )
        db.session.commit()

