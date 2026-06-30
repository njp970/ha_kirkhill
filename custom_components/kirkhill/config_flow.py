"""Config and options flow for the Kirk Hill Wind Farm integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    KirkhillAuthError,
    KirkhillClient,
    KirkhillError,
    KirkhillPasswordChangeRequired,
)
from .const import (
    ALLOWED_RANGES,
    CONF_API_KEY,
    CONF_RANGE,
    CONF_SCAN_MINUTES,
    DEFAULT_RANGE,
    DEFAULT_SCAN_MINUTES,
    DOMAIN,
    MAX_SCAN_MINUTES,
    MIN_SCAN_MINUTES,
    NAME,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


async def _validate_key(hass, api_key: str) -> dict[str, str]:
    """Return a dict of {error_field: code}; empty means the key works."""
    client = KirkhillClient(api_key, async_get_clientsession(hass))
    try:
        await client.async_get_summary()
    except KirkhillAuthError:
        return {"base": "invalid_auth"}
    except KirkhillPasswordChangeRequired:
        return {"base": "password_change_required"}
    except KirkhillError:
        return {"base": "cannot_connect"}
    except Exception:  # noqa: BLE001 - surface anything unexpected as "unknown"
        _LOGGER.exception("Unexpected error validating Kirk Hill API key")
        return {"base": "unknown"}
    return {}


class KirkhillConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # Single instance is enforced by manifest `single_config_entry`; HA
        # aborts a second flow before this step is reached.
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate_key(self.hass, user_input[CONF_API_KEY])
            if not errors:
                return self.async_create_entry(title=NAME, data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate_key(self.hass, user_input[CONF_API_KEY])
            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_API_KEY: user_input[CONF_API_KEY]},
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> KirkhillOptionsFlow:
        return KirkhillOptionsFlow()


class KirkhillOptionsFlow(OptionsFlow):
    """Poll interval + default live range."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # NumberSelector yields a float; store scan_minutes as an int.
            user_input[CONF_SCAN_MINUTES] = int(user_input[CONF_SCAN_MINUTES])
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_MINUTES,
                    default=options.get(CONF_SCAN_MINUTES, DEFAULT_SCAN_MINUTES),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_MINUTES,
                        max=MAX_SCAN_MINUTES,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
                vol.Required(
                    CONF_RANGE,
                    default=options.get(CONF_RANGE, DEFAULT_RANGE),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=ALLOWED_RANGES,
                        translation_key="range",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
