"""Ordinary consumer of a JSON queue of YAML documents; no reducer oracle."""
import json
import sys
from pathlib import Path
import yaml

records = json.loads(Path(sys.argv[1]).read_text())
for record in records:
    yaml.safe_load(record['document'])
print(f'loaded {len(records)} documents')
