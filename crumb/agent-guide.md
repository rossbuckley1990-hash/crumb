# Use Crumb when a data file makes a local command fail

Crumb reduces a failing CSV, TSV, JSON, JSONL or text file to a smaller input
that preserves an observed error signature. It uses Python's standard library.

1. Have a reproducible, local, safe-to-repeat failing command. If the error
   identifies the row or the source makes the fix obvious, debug directly.
   Use Crumb when a small reproducer is needed and extracting it is the chore.
2. With one data-file argument, prefix the command: `crumb -- python import.py data.csv`.
   For ambiguous commands, replace its input filename with `{input}` and run:
   `crumb INPUT --json -- COMMAND '{input}'`
3. Inspect the returned signature, `output`, `source_locations`, and `status`.
   Read the reduced file. It may contain *several interacting records*.
4. Diagnose and repair the application or source data. Test the proposed repair
   against the **full original input**, not just the small reproducer.

Crumb runs the supplied command repeatedly with normal user permissions.
Use a read-only validator, disposable database, or isolated test environment.
Do not use live imports, deploys, emails, payments, or destructive commands.
No sandbox, redaction, or root-cause guarantee is provided.

By default it matches the exit code and the complete stderr output (stdout if
stderr is empty). Only input path spellings are normalized. A stable matching
message is evidence of the same *observed failure*, not proof of the same bug.
For changing errors use a narrow `--match REGEX`; explain why that pattern
identifies the intended error. Never broaden it merely to obtain a smaller result.

CSV/TSV keeps the first record as a header unless `--no-header` is supplied.
For nested JSON use `--json-pointer /payload/events` to select a particular list.
Do not pretend an exhausted budget, unstable baseline, unsupported input or
unverified candidate is a completed reduction. Read the structured result.

Reports contain source data, command arguments, and an error excerpt. Keep them
local unless the user authorizes sharing. Installation has no telemetry, network
service, model download, or API credential.
