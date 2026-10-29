# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Versions follow [semantic versioning](https://semver.org/).

## [Unreleased]

- Initial version.
- A message that cannot be read no longer stops the relay: it is logged and skipped, and values of the wrong type are ignored.
- A connection that drops at once is retried more and more slowly instead of every second.
- Tests, `AGENTS.md`, and a test job in the workflow.
