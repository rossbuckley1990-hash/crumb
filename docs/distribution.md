# Distribution that starts with a useful result

## The promise

“Put `crumb --` before the command that crashes on your data. Get a tiny input
that still reproduces its error.”

Keep that sentence, one real command, the 12,000 → 2 synthetic demo, and the
actual retained CSV above the fold. Do not lead with ddmin, a protocol, a
dashboard, test counts, or a claim that Crumb makes an agent more intelligent.

## Initial users

Developers maintaining data imports, support engineers requesting minimal bug
examples, and people using coding agents with unwieldy CSV/JSON payloads.
The initial job is **extract a small reproducer without writing a reduction
script**. Agents that can already diagnose the code directly may not benefit.

## Shipped adoption material

- Runnable zero-dependency demo in the package.
- Prefix-your-command interface, explicit input mode for ambiguity.
- Agent-readable install URL and `crumb agent` usage guide.
- Standalone wheel, source archive, MIT license, issue template and CI definition.
- Offline HTML report that embeds small reproducers and the JSON report for
  download, keeping the example and source locations together in one file.
- Validation disclosure including the agent trial where the ordinary-tool arm was faster.

No announcements, submissions, outreach messages, artificial votes or stars
were sent as part of development.

## Publish once authenticated

1. Create `rossbuckley1990-hash/crumb`, push the reviewed `main` and tag.
2. Run the committed CI matrix. Do not convert configured jobs into a claim
   that macOS/Windows were tested before they run successfully.
3. Verify a fresh install using the public URL, outside the source directory.
4. Attach the wheel and source archive to a GitHub release with the actual
   checks and limits. The package has not been published to PyPI.
5. Change installation-status wording only after those steps succeed.

## First external test

Offer the install sentence and one concrete example to a small number of
developers who already have a failing import. Ask them to use their own input
locally. Record whether they completed installation, obtained a correct smaller
reproducer, used it to do something useful, and chose to reuse Crumb later.

Suggested continuation threshold: 5 of the first 10 suitable users obtain a
useful reproducer without maintainer intervention, and at least 3 use it again.
These are proposed decision rules, not observed metrics or a validated forecast.

Do not grow the surface until the specific repeated use is established. If
users routinely solve the same task faster with ordinary tools, refine the
target use or stop; more test cases and features will not fix absent demand.

## Contribution loop

Each real input-format failure can become a sanitized regression fixture.
Contributors can add a format with a small example, raw-record preservation
checks and independent reproduction. Keep the maintained public interface small.
