# Crumb 0.1.0 — local release candidate

Crumb reduces a large failing data input while preserving a conservative
observed error match. Prefix an existing command with `crumb --`, or select a
specific input using the explicit `{input}` form.

Includes CSV/TSV logical records, valid JSON/JSONL, UTF-8 line reduction,
bounded executions, two saved-result confirmations, original locations,
machine-readable results, an offline HTML report and a runnable synthetic demo.

45 automated tests passed locally on Linux/Python 3.12.14. Two upstream PyYAML
failure cases were reproduced and reduced from clearly labeled synthetic
expansions. The independent two-agent maintenance trial passed all correctness
gates in both arms; the ordinary-tools agent was faster. No general productivity
or market-success claim is made.

The code runs supplied commands with normal user permissions; it is not a
sandbox. Linux is the locally tested platform. CI for macOS/Windows is provided
but must run after publication. GitHub publication and public-URL installation
remain pending authentication; this is not a published release announcement.
