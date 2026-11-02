# Fast Matter switch: project instructions

- Domain `fast_matter_switch`. `__init__.py`: a relay that keeps a second WebSocket connection to the Matter server
  (the address comes from the Matter integration's config entry) and fires each Matter Generic Switch event as `fast_matter_switch_event`. `event.py`: one device-less event entity per Matter button
  (`press`, `double_press`, `long_press`; the rule that the second touch of a double press is not a press lives in `__init__._fast_event_type` and `const.DOUBLE_TOUCH_MS`), for automations built in the editor. No options.
- It reads the Matter integration's entity registry entries to name the button (`entity_id`, `device_id`); that relies on the unique id format
  `<fabric>-<node as 16 hex digits>-MatterNodeDevice-<endpoint>-GenericSwitch-59-1`, checked against a real installation on 2026-10-29. If a Home Assistant update changes it,
  `_button_entity` and the id in `tests/conftest.py` are the two places to change.
- Tests: `uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python pytest-homeassistant-custom-component==0.13.375 ruff`, then `.venv/bin/python -m pytest` and
  `.venv/bin/ruff check . && .venv/bin/ruff format --check .`. The tests run a real WebSocket server standing in for the Matter server; nothing is mocked inside the integration.
- Nothing reaches the network except the Matter server's own address. No new dependency without asking the owner.
- Licence GPL-3.0-or-later; Python files start with the SPDX line. Public at https://github.com/bora-yarkin/fast-matter-switch, installed through HACS as a custom repository (not in the HACS default list, and not planned to be). A release is a tag `vX.Y.Z` plus a GitHub release whose version matches `manifest.json`.
