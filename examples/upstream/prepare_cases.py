"""Generate explicitly synthetic stress embeddings of public upstream bug repros."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Public issue's original minimal input, unaltered except a final line ending.
(ROOT / 'pyyaml-898-original.yaml').write_text('0x_\n')
(ROOT / 'pyyaml-933-original.yaml').write_text('!!bool "maybe"\n')

# Synthetic workloads, not the upstream reporter's production data.
lines = [f'service_{i:05d}: value_{i:05d}\n' for i in range(8192)]
lines[6107] = 'service_06107: 0x_\n'
(ROOT / 'pyyaml-898-synthetic-8192.yaml').write_text(''.join(lines))

records = [{'name': f'service_{i:05d}', 'document': f'port: {8000 + i}\n'} for i in range(4096)]
records[3017]['document'] = 'enabled: !!bool "maybe"\n'
(ROOT / 'pyyaml-933-synthetic-4096.json').write_text(json.dumps(records, indent=2) + '\n')

# This primary-source behavior is intentionally outside normal JSON decoding.
# It is a reducer-input error case, not a successful minimization demonstration.
(ROOT / 'cpython-154533-integer.json').write_text('{"number":' + '7' * 4301 + '}\n')

print('Prepared two original upstream repro inputs, two synthetic stress embeddings, one parser-limit probe.')
