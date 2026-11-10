# Working on Crumb

Keep the product small: existing failing command → smaller input preserving its
observed failure. Standard-library Python 3.10+, no runtime dependencies.

Use `python3 -m unittest discover -s tests -v` and exercise the actual CLI.
Do not weaken the default full-output fingerprint to produce prettier numbers.
Always verify saved reproducers at their final path, retain source locations,
and distinguish incomplete reductions from minimality.

Synthetic fixtures, upstream reproductions and customer evidence are different.
Label each honestly. A passing suite does not demonstrate product-market fit.
Do not modify existing user input or publish it as part of a test.
