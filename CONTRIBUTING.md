# Contributing

The most valuable contribution is a real failure that Crumb reduces incorrectly
or cannot reduce usefully. Include a small sanitized input, safe-to-repeat command,
expected diagnostic, observed result, OS and Python version. Keep private data,
tokens and customer information out of reports.

Run `python3 -m unittest discover -s tests -v` before proposing a change.
Preserve the zero-runtime-dependency core and the existing-command interface.
Keep comparisons conservative. A smaller input causing a different error is a
regression, even when it makes the demo look better.

Do not add automatic fixes, cloud uploads, telemetry, or automatic execution
of commands embedded in downloaded reports. Propose new formats with a real
case and tests for record boundaries and the saved result's reproducibility.

The project is MIT licensed. By contributing you agree your contribution may
be distributed under that license.
