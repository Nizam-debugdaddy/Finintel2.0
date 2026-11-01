from pathlib import Path
import os

# Project root is backend/
ROOT = Path(__file__).resolve().parent.parent

class Settings:
    WAREHOUSE_PATH: Path = Path(os.environ.get("WAREHOUSE_PATH", str(ROOT / "warehouse")))
    MAPPINGS_PATH:  Path = ROOT / "mappings"
    LEGACY_PATH:    Path = ROOT / "legacy_engines"
    SRC_PATH:       Path = ROOT / "src"
    OUTPUT_PATH:    Path = Path(os.environ.get("OUTPUT_PATH", str(ROOT / "output")))
    DB_PATH:        str  = os.environ.get("DB_PATH", str(ROOT / "metadata.db"))
    DATABASE_URL:   str  = os.environ.get("DATABASE_URL", "")
    ALLOWED_ORIGINS: list = [
        o.strip() for o in os.environ.get(
            "ALLOWED_ORIGINS", "https://fin-intel.vercel.app"
        ).split(",") if o.strip()
    ]

settings = Settings()
