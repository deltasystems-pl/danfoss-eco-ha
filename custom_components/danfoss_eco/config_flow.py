"""Config flow: discover an eTRV, guide the button press, read the key."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .ble import EtrvButtonNotPressed, EtrvClient, EtrvError, EtrvNotFoundError
from homeassistant.const import CONF_ADDRESS

from .const import (
    CONF_AUTO_TIME_SYNC,
    CONF_PIN,
    CONF_POLL_INTERVAL,
    CONF_SECRET_KEY,
    DANFOSS_OUI,
    DEFAULT_AUTO_TIME_SYNC,
    DEFAULT_PIN,
    DEFAULT_POLL_INTERVAL_MIN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

MANUAL_ENTRY = "__manual__"
_KEY_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def _is_etrv(info: BluetoothServiceInfoBleak) -> bool:
    return info.address.upper().startswith(DANFOSS_OUI) or (
        info.name or ""
    ).endswith(";eTRV")


class DanfossEcoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Wizard: pick device -> press button -> key retrieved -> done."""

    VERSION = 1

    def __init__(self) -> None:
        self._address: str | None = None
        self._adv_name: str | None = None

    # -- discovery entry point ---------------------------------------------
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._adv_name = discovery_info.name
        self.context["title_placeholders"] = {"name": discovery_info.address}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_pair_menu()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"address": self._address or ""},
        )

    async def async_step_pair_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose automatic pairing or manual key entry."""
        return self.async_show_menu(
            step_id="pair_menu", menu_options=["pair", "manual_key"]
        )

    # -- manual entry point -------------------------------------------------
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            choice = user_input["device"]
            if choice == MANUAL_ENTRY:
                return await self.async_step_manual()
            self._address = choice
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return await self.async_step_pair_menu()

        candidates = {
            info.address: f"{info.address} ({info.name or 'eTRV'})"
            for info in bluetooth.async_discovered_service_info(self.hass, False)
            if _is_etrv(info)
        }
        current = {e.unique_id for e in self._async_current_entries()}
        candidates = {a: n for a, n in candidates.items() if a not in current}
        # No thermostat detected yet: keep the guided (button-press) wizard as the
        # primary path - offer to search again after waking the device - and keep
        # manual address/key entry only as an advanced fallback.
        if not candidates:
            return await self.async_step_no_devices()
        # Devices found: pick one to pair. Manual entry stays as an extra option.
        candidates[MANUAL_ENTRY] = "✏️  Enter address and key manually (advanced)"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("device"): vol.In(candidates)}),
        )

    async def async_step_no_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Shown when nothing is advertising: search again or add manually."""
        return self.async_show_menu(
            step_id="no_devices", menu_options=["rescan", "manual"]
        )

    async def async_step_rescan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-run discovery (after the user woke the thermostat)."""
        return await self.async_step_user()

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a thermostat by typing its MAC address and secret key.

        For devices that aren't advertising right now, or when migrating a key
        from etrv2mqtt / libetrv without touching the thermostat.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            key = user_input[CONF_SECRET_KEY].strip().lower()
            if not _MAC_RE.match(address):
                errors[CONF_ADDRESS] = "invalid_address"
            elif not _KEY_RE.match(key):
                errors[CONF_SECRET_KEY] = "invalid_key"
            else:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                pin = int(user_input.get(CONF_PIN) or 0)
                return self.async_create_entry(
                    title=f"Danfoss Eco {address[-5:]}",
                    data={
                        "address": address,
                        CONF_SECRET_KEY: key,
                        CONF_PIN: pin,
                    },
                )
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS, default=self._address or ""): str,
                    vol.Required(CONF_SECRET_KEY): str,
                    vol.Optional(CONF_PIN, default=0): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=9999)
                    ),
                }
            ),
            errors=errors,
        )

    # -- the pairing wizard step -------------------------------------------
    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._address
        errors: dict[str, str] = {}
        if user_input is not None:
            client = EtrvClient(self.hass, self._address, None, DEFAULT_PIN)
            try:
                key = await client.retrieve_secret_key()
            except EtrvButtonNotPressed:
                errors["base"] = "button_not_pressed"
            except EtrvNotFoundError:
                errors["base"] = "not_in_range"
            except EtrvError:
                errors["base"] = "cannot_connect"
            else:
                name = await client.read_name() or f"Danfoss Eco {self._address[-5:]}"
                return self.async_create_entry(
                    title=name,
                    data={
                        "address": self._address,
                        CONF_SECRET_KEY: key.hex(),
                        CONF_PIN: DEFAULT_PIN,
                    },
                )
        return self.async_show_form(
            step_id="pair",
            errors=errors,
            description_placeholders={"address": self._address},
            last_step=True,
        )

    # -- reconfigure an existing entry (update key / PIN) -------------------
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_SECRET_KEY].strip().lower()
            if not _KEY_RE.match(key):
                errors[CONF_SECRET_KEY] = "invalid_key"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_SECRET_KEY: key,
                        CONF_PIN: int(user_input.get(CONF_PIN) or 0),
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SECRET_KEY, default=entry.data.get(CONF_SECRET_KEY, "")
                    ): str,
                    vol.Optional(
                        CONF_PIN, default=entry.data.get(CONF_PIN, DEFAULT_PIN)
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=9999)),
                }
            ),
            errors=errors,
            description_placeholders={"address": entry.data.get("address", "")},
        )

    # -- manual key fallback ------------------------------------------------
    async def async_step_manual_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._address
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_SECRET_KEY].strip()
            if not _KEY_RE.match(key):
                errors[CONF_SECRET_KEY] = "invalid_key"
            else:
                return self.async_create_entry(
                    title=f"Danfoss Eco {self._address[-5:]}",
                    data={
                        "address": self._address,
                        CONF_SECRET_KEY: key.lower(),
                        CONF_PIN: DEFAULT_PIN,
                    },
                )
        return self.async_show_form(
            step_id="manual_key",
            data_schema=vol.Schema({vol.Required(CONF_SECRET_KEY): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "DanfossEcoOptionsFlow":
        return DanfossEcoOptionsFlow()


class DanfossEcoOptionsFlow(OptionsFlow):
    """Options: poll interval, PIN, auto time sync."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=opts.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_MIN),
                    ): vol.All(int, vol.Range(min=1, max=180)),
                    vol.Required(
                        CONF_PIN,
                        default=opts.get(
                            CONF_PIN,
                            self.config_entry.data.get(CONF_PIN, DEFAULT_PIN),
                        ),
                    ): vol.All(int, vol.Range(min=0, max=9999)),
                    vol.Required(
                        CONF_AUTO_TIME_SYNC,
                        default=opts.get(CONF_AUTO_TIME_SYNC, DEFAULT_AUTO_TIME_SYNC),
                    ): bool,
                }
            ),
        )
