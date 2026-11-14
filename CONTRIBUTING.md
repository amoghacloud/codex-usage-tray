# Contributing

Mac and Windows previews need testing from people who use those platforms.
Bug reports and pull requests are welcome.

Include your OS version, architecture, Codex CLI version, app version, and
steps to reproduce. Say whether the issue occurs in demo mode or only with a
signed-in account. Use fictional accounts in screenshots and fixtures.

Run the shared tests with `python -m unittest discover -s tests -v`. For
desktop changes, install PySide6 and run `python desktop.py --demo` on the
affected OS. If your change touches login or usage, compare the current
account, reset times, and a switch between two accounts against Codex.

GitHub Actions builds on macOS and Windows and checks the offline demo menu.
Please report which native interactions you verified in your pull request.
