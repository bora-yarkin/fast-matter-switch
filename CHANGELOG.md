# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Versions follow [semantic versioning](https://semver.org/).

## [Unreleased]

## [0.5.0]

- The `fast_matter_switch_event` bus event carries `fast_event_type` (`press`, `double_press` or `long_press`) when the button's event entity reports something for it, so other integrations can use the same rule without repeating it.

## [0.4.2]

- Installation notes now describe the Marketplace that replaces HACS in Home Assistant 2026.11. No change in behaviour.

## [0.4.1]

- The manifest keys are in the order Home Assistant's validation (hassfest) requires. No change in behaviour.

## [0.4.0]

- Latching switches (rockers that stay in a position) are reported on the event bus as `switch_latched`, with the `position` they moved to.
- Documentation for every Matter switch: installation with HACS as a custom repository or by hand, automations in the editor and in YAML, the bus event's fields, troubleshooting.
- The repository is public: manifest links point at it.

## [0.3.0]

- Every Matter button gets an event entity (`event.<button>_fast`) that reports `press`, `double_press` and `long_press`, so an automation can use the editor's **Event received** trigger with no YAML. The second touch of a double press, or a press a switch reports twice (within 800 ms of the last touch), is not reported as a `press`. The entity follows the Matter button: added with it, removed with it. The bus event is unchanged.
- Initial version.
- A message that cannot be read no longer stops the relay: it is logged and skipped, and values of the wrong type are ignored.
- A connection that drops at once is retried more and more slowly instead of every second.
- Tests, `AGENTS.md`, and a test job in the workflow.
