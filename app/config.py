import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    DATABASE_URL = os.getenv("DATABASE_URL")
    GEN_AI_KEY = os.getenv("GEN_AI_KEY")
    DB_MAX_CONN = int(os.getenv("DB_MAX_CONN", "20"))
    PDF_BG_WORKERS = int(os.getenv("PDF_BG_WORKERS", "2"))

class DevelopmentConfig(Config):
    DEBUG = True