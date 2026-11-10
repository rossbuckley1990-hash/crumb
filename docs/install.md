# Install Crumb and prove the first result

This is an agent-readable installation guide. Crumb reduces local failing data
inputs. It does not give the agent internet access, credentials or extra authority.

## Install

If you already have this repository, use that source. Otherwise, after the GitHub
repository has been published, install from the exact repository below. The
`crumb` package name on a public package index may refer to somebody else.

If `uv` is already available:

```bash
uv tool install 'git+https://github.com/rossbuckley1990-hash/crumb'
crumb doctor
crumb demo
crumb agent
```

Otherwise, Python 3.10+ and a local checkout are sufficient to run it without
installation:

```bash
git clone https://github.com/rossbuckley1990-hash/crumb.git
cd crumb
python3 -m crumb doctor
python3 -m crumb demo
python3 -m crumb agent
```

An extracted source archive works the same way: run those last three commands
from its root. On Windows, `py -3` or `python` may be the interpreter command.
Do not install system packages or change the user's agent configuration just
because this document suggests an optional convenience.

## Verify the first useful result

The built-in demo creates 12,000 synthetic CSV records and a local importer
using an in-memory SQLite database. It intentionally includes two distant
records that conflict after normalization.

Read `crumb-demo/result/report.json` and the saved CSV. Check:

- `verified_final` and `source_unchanged` are true;
- 12,000 input units reduce to 2 output units;
- the source locations identify both retained records;
- the actual error is SQLite's uniqueness failure, not a parser failure.

Show the user the tiny example and the report. Explain that this is a synthetic
demo. Do not present it as proof of market demand or benchmark superiority.

## Apply it

Use an existing reproducible, safe-to-repeat local command. Replace its input
filename with a literal `{input}` argument. Read `crumb agent` before the first
real use. Never run a live import or other side-effectful operation repeatedly.
Reports remain local; do not upload them without authorization.

## Update and remove

For a uv installation, repeat the exact `uv tool install` command with
`--reinstall`. Uninstall with `uv tool uninstall crumb-reducer`.
For a source checkout, use normal Git updates. A downloaded source directory
has no daemon, browser integration, telemetry or hidden state to uninstall.
Keep or remove its output folders according to the user's wishes.

## Distribution status

Local source and wheel installation are part of the validation process. The
GitHub install URL becomes usable only after repository publication. Do not
claim a successful remote install unless it was actually performed.
