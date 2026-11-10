"""An ordinary YAML-consuming command. No reducer-specific oracle or assertion."""
import sys
from pathlib import Path
import yaml

data = yaml.safe_load(Path(sys.argv[1]).read_text())
print(f'loaded {len(data) if isinstance(data, (dict, list)) else 1} entries')
