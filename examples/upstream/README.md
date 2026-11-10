# Reproducing the upstream cases

These examples require PyYAML 6.0.3, used only by the target consumers. It is not
a Crumb dependency. They reproduce previously reported issues, not new findings.

- https://github.com/yaml/pyyaml/issues/898 — malformed hexadecimal scalar.
- https://github.com/yaml/pyyaml/issues/933 — invalid explicitly typed boolean.

Run `python3 examples/upstream/prepare_cases.py`. It writes the tiny original
inputs and two **synthetic stress embeddings** beside itself. Then run from the
repository root:

```bash
python3 -m crumb examples/upstream/pyyaml-898-synthetic-8192.yaml --format lines -- python3 examples/upstream/load_yaml.py '{input}'
python3 -m crumb examples/upstream/pyyaml-933-synthetic-4096.json -- python3 examples/upstream/load_yaml_queue.py '{input}'
```

The generator also makes a 4,301-digit JSON integer, based on CPython issue
https://github.com/python/cpython/issues/154533 (closed as not planned). It is a
graceful input-refusal case, not a successful reduction demonstration.
