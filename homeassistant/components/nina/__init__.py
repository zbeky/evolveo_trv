"""The Nina integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from async_timeout import timeout
from pynina import ApiError, Nina

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import _LOGGER, CONF_FILTER_CORONA, CONF_REGIONS, DOMAIN, SCAN_INTERVAL

PLATFORMS: list[str] = [Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up platform from a ConfigEntry."""

    regions: dict[str, str] = entry.data[CONF_REGIONS]

    coordinator = NINADataUpdateCoordinator(
        hass, regions, entry.data[CONF_FILTER_CORONA]
    )

    await coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


@dataclass
class NinaWarningData:
    """Class to hold the warning data."""

    id: str
    headline: str
    description: str
    sender: str
    severity: str
    sent: str
    start: str
    expires: str
    is_valid: bool


class NINADataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching NINA data API."""

    def __init__(
        self, hass: HomeAssistant, regions: dict[str, str], corona_filter: bool
    ) -> None:
        """Initialize."""
        self._regions: dict[str, str] = regions
        self._nina: Nina = Nina(async_get_clientsession(hass))
        self.warnings: dict[str, Any] = {}
        self.corona_filter: bool = corona_filter

        for region in regions:
            self._nina.addRegion(region)

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data."""
        async with timeout(10):
            try:
                await self._nina.update()
            except ApiError as err:
                raise UpdateFailed(err) from err
            return self._parse_data()

    def _parse_data(self) -> dict[str, Any]:
        """Parse warning data."""

        return_data: dict[str, Any] = {}

        for region_id, raw_warnings in self._nina.warnings.items():
            warnings_for_regions: list[NinaWarningData] = []

            for raw_warn in raw_warnings:
                if "corona" in raw_warn.headline.lower() and self.corona_filter:
                    continue

                warning_data: NinaWarningData = NinaWarningData(
                    raw_warn.id,
                    raw_warn.headline,
                    raw_warn.description,
                    raw_warn.sender,
                    raw_warn.severity,
                    raw_warn.sent or "",
                    raw_warn.start or "",
                    raw_warn.expires or "",
                    raw_warn.isValid(),
                )
                warnings_for_regions.append(warning_data)

            return_data[region_id] = warnings_for_regions

        return return_data
