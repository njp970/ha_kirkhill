"""The Kirk Hill Wind Farm integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KirkhillClient
from .const import CONF_API_KEY, CONF_RANGE, DEFAULT_RANGE
from .coordinator import KirkhillCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type KirkhillConfigEntry = ConfigEntry[KirkhillCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: KirkhillConfigEntry) -> bool:
    """Set up Kirk Hill from a config entry."""
    client = KirkhillClient(
        entry.data[CONF_API_KEY],
        async_get_clientsession(hass),
        default_range=entry.options.get(CONF_RANGE, DEFAULT_RANGE),
    )
    coordinator = KirkhillCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KirkhillConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_on_update(
    hass: HomeAssistant, entry: KirkhillConfigEntry
) -> None:
    """Reload when options (poll interval / range) change."""
    await hass.config_entries.async_reload(entry.entry_id)
