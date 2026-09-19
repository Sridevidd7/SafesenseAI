import json
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent.parent / 'logs' / 'llm_logs.jsonl'

def log_llm_event(event: dict):
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        event['timestamp'] = datetime.utcnow().isoformat()
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        print(f'[LLM Logger] Error writing log: {e}')

