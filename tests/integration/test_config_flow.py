"""Config + options + reauth flow tests."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.kirkhill.api import (
    KirkhillApiError,
    KirkhillAuthError,
    KirkhillPasswordChangeRequired,
)
from custom_components.kirkhill.const import (
    CONF_API_KEY,
    CONF_RANGE,
    CONF_SCAN_MINUTES,
    DOMAIN,
    NAME,
)


async def test_user_flow_success(hass: HomeAssistant, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "kh_test_key"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_API_KEY: "kh_test_key"}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (KirkhillAuthError("bad"), "invalid_auth"),
        (KirkhillPasswordChangeRequired("423"), "password_change_required"),
        (KirkhillApiError("boom"), "cannot_connect"),
        (RuntimeError("?"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, mock_client, error, expected
) -> None:
    mock_client.async_get_summary.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "kh_test_key"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_single_instance_aborts(
    hass: HomeAssistant, mock_client, mock_entry
) -> None:
    # manifest `single_config_entry` makes HA abort before the user step.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow(hass: HomeAssistant, mock_client, mock_entry) -> None:
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_MINUTES: 10, CONF_RANGE: "today"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_entry.options == {CONF_SCAN_MINUTES: 10, CONF_RANGE: "today"}
    # scan_minutes must be coerced to int (NumberSelector yields float)
    assert isinstance(mock_entry.options[CONF_SCAN_MINUTES], int)


async def test_reauth_flow_updates_key(
    hass: HomeAssistant, mock_client, mock_entry
) -> None:
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    result = await mock_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "kh_new_key"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_entry.data[CONF_API_KEY] == "kh_new_key"
