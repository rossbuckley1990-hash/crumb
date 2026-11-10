# What was actually verified

Date: 10 November 2026. Local environment: Linux, Python 3.12.14.

**Verdict:** Crumb works as a small data-reduction utility in the cases below.
There is no evidence yet of adoption or market success. The paired agent trial
did not demonstrate better end-task outcomes or a speed advantage over ordinary
tools. This limitation is part of the result, not omitted from the release.

## Automated checks

`python3 -m unittest discover -s tests -v`: **45 tests pass**.

- 24 focused core tests.
- 18 independently written blackbox CLI acceptance tests.
- 3 first-use tests, including prefix inference, ambiguous inputs, an empty
  selection hint and byte-exact embedded report downloads.

They cover distant interacting records, BOM/CRLF and multiline CSV, escaped
JSON pointers, required JSON structure, whole JSONL records, full-output
error matching, hostile HTML text, invalid UTF-8 diagnostics, literal shell
arguments, timeouts and POSIX child cleanup, output bounds, original/candidate
mutation detection, budget accounting, input errors, and final-path verification.

See [the final test log](evidence/final-tests.log). Tests characterize these
cases; they do not establish a sandbox or universal semantic equivalence.

## Actual self-use

| Case | Input | Saved result | Command executions | Observed elapsed |
| --- | --- | --- | --- | --- |
| Synthetic inventory import with two distant normalized-SKU collisions | 12,000 CSV data records; 431,559 bytes | 2 records; 92 bytes | 75 | 2.5665 s |
| PyYAML #898 embedded in a synthetic YAML mapping | 8,192 entries; 221,176 bytes | 1 line; 19 bytes | 22 | 2.7209 s |
| PyYAML #933 embedded in a synthetic JSON queue | 4,096 records; 284,737 bytes | 1 record; 87 bytes | 23 | 2.3873 s |
| Independent constructed order-import task | 6,002 records; 268,233 bytes | 2 records; 145 bytes | 64 | 3.4827 s |

These are observations on one machine, not promises or comparisons against
other reducers. Every saved result matched the selected diagnostic twice, and
every original content hash was unchanged.

Raw first-run reports are under [evidence](evidence/). The installed-wheel
prefix-command recheck is also preserved there. Later improvements retained
the same two-record inventory witness.

The PyYAML cases reproduce previously published issues
[#898](https://github.com/yaml/pyyaml/issues/898) and
[#933](https://github.com/yaml/pyyaml/issues/933), using PyYAML 6.0.3 as the
**target program's** dependency. They are not new bug discoveries or production
datasets. Generators and ordinary consumer commands are in
[examples/upstream](../examples/upstream/README.md).

Two proposed CPython CSV Sniffer cases did not reproduce in this environment
and were excluded. A 4,301-digit JSON integer based on CPython
[#154533](https://github.com/python/cpython/issues/154533) is an input-refusal
probe, not a successful reduction case; that upstream issue was closed as not planned.

## Independent comparison with ordinary tools

An independent agent prepared identical 6,002-record order-import workspaces,
an explicit business policy, and six predetermined correctness gates. Two fresh
agents received the same source and data. One had ordinary terminal/Python tools;
the other also had Crumb. Neither saw the independent evaluator. Source was not
hidden to make the baseline weaker.

Task: produce a compact reproducer, diagnose and fix the importer, write a
regression check, and verify the full original data. The source incorrectly
omitted the supplier from an order-line identity.

| Observation | Ordinary tools | Crumb available |
| --- | --- | --- |
| Independent correctness gates | 6/6 pass | 6/6 pass |
| Compact reproducer | 2 records, 145 bytes | 2 records, 145 bytes |
| Full data accepted correctly | Yes | Yes |
| Real conflicts still rejected | Yes | Yes |
| Original data unchanged | Yes | Yes |
| Self-recorded time to full verification | 77.723 s | 398 s |
| Shell execution tool calls | 5 | 7, plus 1 poll |
| Reducer subprocess calls | None | 64 |

The treatment agent reported noticing the source defect before reduction
finished. Crumb supplied the compact fixture automatically, but the task did
not need that reduction to discover the fix. Analysis and reporting overhead
were substantial in the treatment arm. One task and two model runs do not
isolate a causal timing effect or justify population claims.

**Conclusion: no demonstrated end-task advantage here.** We narrowed the usage
guide to occasions where extracting the reproducer is actually the chore.
Crumb should not be applied reflexively to an already obvious defect.

Both original workspaces, reports, the task, predeclared design and independent
evaluator are in [examples/value-trial](../examples/value-trial/).
The parent's independent evaluations are
[ordinary tools](evidence/baseline-oracle.json) and
[with Crumb](evidence/crumb-oracle.json).

## Critiques that changed the implementation

1. **Different errors can share a final line.** Replaced the proposed last-line
   fingerprint with complete normalized diagnostic bytes and return code.
   A blackbox case now rejects `missing header / import failed` when the intended
   failure is `duplicate record / import failed`.
2. **A visual diagnostic string can hide different raw bytes.** Exact comparison
   also hashes normalized raw output, separating malformed UTF-8 from literal
   escape text.
3. **Newlines and records differ.** CSV uses the parser's physical-line ranges
   and retains raw record bytes; vertical tabs and quoted multiline fields
   cannot silently change its reconstruction.
4. **A temporary candidate is not the final file.** The full roundtrip and two
   uncached runs at the saved output path catch formatting and filename dependence.
5. **The first command was needlessly fiddly.** Added `crumb -- <existing command>`
   for exactly one identifiable input file. Multiple candidates are refused
   rather than guessed.
6. **An empty selection can expose a setup failure.** The result now points to
   setup, a retained header or a JSON envelope when no selected units are needed.
7. **Sharing an HTML file lost its adjacent downloads.** Small reproducers
   (up to 1 MiB) and the JSON report are now embedded as byte-exact downloads.
8. **A good reduction is not automatically better agent work.** Preserved the
   negative comparison result and narrowed the agent guidance.

## Installation and delivery checks

- Built a standalone wheel from the source with no runtime requirements.
- Installed it without an index or dependencies into a fresh virtual environment.
- Ran the installed `crumb doctor`, demo, prefix-command reduction and `crumb agent`
  from outside the source checkout.
- The source tree works directly with `python3 -m crumb`.
- The release includes the complete source, tests, evidence, MIT license and
  pinned-action CI definition. No paid service is required by Crumb itself.

## Remaining limits

- **Remote publication is pending.** The available GitHub connector has file
  and Git-object writes but no repository-creation action. The local GitHub CLI
  is unauthenticated, the connected local browser is unavailable, and the cloud
  browser is at GitHub sign-in. No public repository, registry release or public
  install success is claimed.
- **Cross-platform CI has not run.** Linux/Python 3.12 is the observed runtime;
  macOS, Windows and other configured Python versions remain unverified.
- **Browser rendering was not verified.** A local Chromium launch was blocked
  from creating a Unix socket; escalation was rejected by the environment's
  approval policy. The cloud browser disallowed the local-file URL. Report
  escaping and embedded bytes were tested, but screenshots/layout were not.
- No external users, repeat-use data, conversion metrics, star growth or paid
  demand have been observed. The stronger aspiration of proven product success
  is not met by this development session.
