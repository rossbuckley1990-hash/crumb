# Security boundaries

Crumb runs the command you supply, repeatedly, with your existing environment,
working directory, credentials and permissions. It is **not a sandbox**.
Use read-only validation or disposable targets. Never pass a command taken from
untrusted data without reviewing it.

Crumb uses `shell=False`; placeholder replacement changes argv values, not
shell syntax. POSIX timeouts terminate the command's process group; detached
processes and external side effects are outside that guarantee. Windows cleanup
covers the direct process. Output capture is bounded to 1 MiB per stream.

Source and candidate hashes detect commands that change their input. They do
not undo such a change. Use backups for important inputs. No claim is made about
malicious concurrent writers, hostile filesystem races, or arbitrary processes.

Reports include data, paths, command arguments and diagnostic output. They are
not redacted. HTML output escapes untrusted text, contains no script, and makes
no external network requests. The supplied command may use the network.

Report a security concern privately through GitHub's private vulnerability
reporting if it is enabled. Otherwise use a sanitized issue requesting a private
contact; do not post credentials or private reproducer data.
