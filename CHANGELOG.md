# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Versions follow [semantic versioning](https://semver.org/).

## [Unreleased]

- Every Matter button gets an event entity (`event.<button>_fast`) that reports `press`, `double_press` and `long_press`, so an automation can use the editor's **Event received** trigger with no YAML. The second touch of a double press, or a press a switch reports twice (within 800 ms of the last touch), is not reported as a `press`. The entity follows the Matter button: added with it, removed with it. The bus event is unchanged.
- Initial version.
- A message that cannot be read no longer stops the relay: it is logged and skipped, and values of the wrong type are ignored.
- A connection that drops at once is retried more and more slowly instead of every second.
- Tests, `AGENTS.md`, and a test job in the workflow.
