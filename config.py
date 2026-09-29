import os


class BaseConfig:
    """Base application configuration."""

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "development-secret-key-change-this"
    )

    UPLOAD_FOLDER = os.getenv(
        "UPLOAD_FOLDER",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "uploads"
        )
    )

    MAX_CONTENT_LENGTH = int(
        os.getenv(
            "MAX_CONTENT_LENGTH",
            50 * 1024 * 1024
        )
    )

    ALLOWED_EXTENSIONS = {
        "pdf",
        "doc",
        "docx"
    }


class DevelopmentConfig(BaseConfig):
    """Local development configuration."""

    DEBUG = True


class ProductionConfig(BaseConfig):
    """Production configuration."""

    DEBUG = False