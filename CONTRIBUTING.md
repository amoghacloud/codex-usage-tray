# Contributing

This project maintains Ubuntu. Bug reports and pull requests are welcome.
Contributors can maintain macOS and Windows distributions in their own forks.

Include your OS version, architecture, Codex CLI version, app version, and
steps to reproduce. Say whether the issue occurs in demo mode or only with a
signed-in account. Use fictional accounts in screenshots and fixtures.

Run the shared tests with `python -m unittest discover -s tests -v`. For
desktop changes, install PySide6 and run `python desktop.py --demo` on the
affected OS. If your change touches login or usage, compare the current
account, reset times, and a switch between two accounts against Codex.

The manual **Community desktop builds** workflow packages unsigned macOS Apple
Silicon and Windows x64 artifacts. Run it from the Actions tab in your fork.
Test the native tray and live account switching before distributing a build.
Use your own signing credentials and publish from your fork.
