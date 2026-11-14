# SPDX-License-Identifier: GPL-3.0-or-later
"""One "Reachable" sensor for each sleepy Matter device (the IKEA BILRESA remotes), linked to that device."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MATTER_DOMAIN
from .coordinator import ReachabilityCoordinator


def matter_device(hass: HomeAssistant, node_id: int) -> dr.DeviceEntry | None:
    """The Home Assistant device of one Matter node, found by the node id in its identifier."""
    marker = f"-{node_id:016X}-MatterNodeDevice"
    for device in dr.async_get(hass).devices:
        # Another integration's identifiers can have more than two parts, so each one is read by position, not unpacked.
        if any(
            identifier[0] == MATTER_DOMAIN and identifier[1].startswith("deviceid_") and identifier[1].endswith(marker)
            for identifier in device.identifiers
            if len(identifier) >= 2
        ):
            return device
    return None


class ReachableSensor(CoordinatorEntity[ReachabilityCoordinator], BinarySensorEntity):
    """On while the device answered its last ping, off when it did not. Unavailable when the Matter server cannot be asked."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    # The entity id is made once, from this name: the area and the device's own name, as the owner's entity ids are
    # (`<area>_<device>_...`). The sensor is then linked to the Matter device in the registry (async_added_to_hass); a device
    # belongs to the Matter config entry alone, so it cannot be named in this entity's device info.
    _attr_has_entity_name = False

    def __init__(self, hass: HomeAssistant, coordinator: ReachabilityCoordinator, node_id: int, device: dr.DeviceEntry) -> None:
        super().__init__(coordinator)
        self._node_id = node_id
        self._device_id = device.id
        area = ar.async_get(hass).async_get_area(device.area_id) if device.area_id else None
        self._attr_name = " ".join(part for part in (area.name if area else None, device.name_by_user or device.name, "Reachable") if part)
        self._attr_unique_id = f"{DOMAIN}-reachable-{node_id}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        registry = er.async_get(self.hass)
        if registry.async_get(self.entity_id).device_id != self._device_id:
            registry.async_update_entity(self.entity_id, device_id=self._device_id)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data[self._node_id].reachable

    @property
    def available(self) -> bool:
        return super().available and self._node_id in self.coordinator.data

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self.coordinator.data[self._node_id].last_reachable if self._node_id in self.coordinator.data else None
        return {"last_reachable": last.isoformat() if last else None}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    known: set[int] = set()

    @callback
    def add_new() -> None:
        new = []
        for node_id in coordinator.data or {}:
            device = None if node_id in known else matter_device(hass, node_id)
            if device is not None:
                known.add(node_id)
                new.append(ReachableSensor(hass, coordinator, node_id, device))
        if new:
            async_add_entities(new)

    entry.async_on_unload(coordinator.async_add_listener(add_new))
    add_new()
