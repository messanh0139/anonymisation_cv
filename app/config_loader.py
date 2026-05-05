"""
config_loader.py
Charge config.yaml une seule fois et expose les paramètres via CFG.
Usage :
    from app.config_loader import CFG
    folder_id = CFG["drive"]["input_folder_id"]
"""
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


@lru_cache(maxsize=1)
def _load() -> dict:
    try:
        import yaml  # type: ignore
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            logger.info("[CONFIG] config.yaml chargé depuis %s", _CONFIG_PATH)
            return data
    except ImportError:
        logger.warning("[CONFIG] PyYAML non installé — valeurs par défaut utilisées")
        return {}
    except FileNotFoundError:
        logger.warning("[CONFIG] config.yaml introuvable — valeurs par défaut utilisées")
        return {}


def get(section: str, key: str, default=None):
    """Récupère CFG[section][key] avec valeur par défaut."""
    return _load().get(section, {}).get(key, default)


# Accès direct au dict complet
CFG: dict = {}


def _init():
    global CFG
    CFG = _load()


_init()
