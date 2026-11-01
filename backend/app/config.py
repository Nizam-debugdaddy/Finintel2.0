from pathlib import Path
import os

# Project root is backend/
ROOT = Path(__file__).resolve().parent.parent

class Settings:
    WAREHOUSE_PATH: Path = ROOT / "warehouse"
    MAPPINGS_PATH:  Path = ROOT / "mappings"
    LEGACY_PATH:    Path = ROOT / "legacy_engines"
    SRC_PATH:       Path = ROOT / "src"
    OUTPUT_PATH:    Path = ROOT / "output"
    DB_PATH:        str  = str(ROOT / "metadata.db")
    ALLOWED_ORIGINS: list = ["*"]

settings = Settings()
