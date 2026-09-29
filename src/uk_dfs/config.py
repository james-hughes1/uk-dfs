"""Project-wide paths. Everything that touches disk should import from here."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"  # untouched downloads, never edited by hand
INTERIM_DIR = DATA_DIR / "interim"  # cleaned/joined intermediate tables
PROCESSED_DIR = DATA_DIR / "processed"  # final model-ready datasets
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"
