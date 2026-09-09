from pathlib import Path
import orjson
from typing import Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent   # project root

BUY_TEMPLATE_PATH = BASE_DIR / "config" / "templates" / "buy_payload_template.json"

def _load_template(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required payload template missing: {path}\n"
        )
    try:
        return orjson.loads(path.read_bytes())
    except Exception as e:
        raise ValueError(f"Invalid JSON in {path}: {e}") from e
    
    
    
    
# Loaded once when this module is imported

BUY_PAYLOAD_TEMPLATE: Dict[str, Any] = _load_template(BUY_TEMPLATE_PATH)




def create_buy_payload(**overrides) -> bytes:
    """Fast way to create + serialize a buy payload."""
    payload = BUY_PAYLOAD_TEMPLATE.copy()
    payload.update(overrides)
    return orjson.dumps(payload)