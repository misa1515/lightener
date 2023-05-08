"""The config flow for Lightener."""

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_FRIENDLY_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get,
)
from homeassistant.helpers.selector import selector

from .const import DOMAIN


class LightenerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Lightener config flow."""

    # The schema version of the entries that it creates.
    # Home Assistant will call the migrate method if the version changes.
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Configure the lighener device name"""

        errors = {}

        if user_input is not None:
            name = user_input["name"]

            data = {}
            data[CONF_FRIENDLY_NAME] = name

            return self.async_create_entry(title=name, data=data)

        data_schema = {
            vol.Required("name"): str,
        }

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(data_schema), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""

        return LightenerOptionsFlow(config_entry)


class LightenerOptionsFlow(config_entries.OptionsFlow):
    """The options flow handler for Lightener."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""

        self.config_entry = config_entry
        self.data = {}
        self.local_data = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manages the selection of the lights controlled by the Lighetner light."""

        # Create a list with the ids of the Lightener entities we're configuring.
        # Most likely we'll have a single item in the list.
        entity_registry = async_get(self.hass)
        lightener_entities = async_entries_for_config_entry(
            entity_registry, self.config_entry.entry_id
        )
        lightener_entities = list(map(lambda e: e.entity_id, lightener_entities))

        # Load the previously configured list.
        controlled_entities = list(self.config_entry.options.get("entities", {}).keys())

        if user_input is not None:
            controlled_entities = self.local_data[
                "controlled_entities"
            ] = user_input.get("controlled_entities")
            entities = self.data["entities"] = {}

            for entity in controlled_entities:
                entities[entity] = {}

            return await self.async_step_light_configuration()

        return self.async_show_form(
            step_id="init",
            last_step=False,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "controlled_entities", default=controlled_entities
                    ): selector(
                        {
                            "entity": {
                                "multiple": True,
                                "filter": {"domain": "light"},
                                "exclude_entities": lightener_entities,
                            }
                        }
                    )
                }
            ),
        )

    async def async_step_light_configuration(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manages the configuration for each controlled light."""

        placeholders = {}
        errors = {}

        controlled_entities = self.local_data.get("controlled_entities")

        if user_input is not None:
            brightness = {}

            for entry in user_input.get("brightness", "").splitlines():
                match = re.fullmatch(r"^(\d+)\s*:\s*(\d+)\s*$", entry)

                if match is not None:
                    left = int(match.group(1))
                    right = int(match.group(2))

                    if left >= 1 and left <= 100 and right <= 100:
                        brightness[left] = str(right)
                        continue

                errors["brightness"] = "invalid_brightness"
                placeholders["error_entry"] = entry
                break

            if len(errors) == 0:
                entities: dict = self.data.get("entities")
                entities.get(self.local_data.get("current_light"))[
                    "brightness"
                ] = brightness

                if len(controlled_entities):
                    return await self.async_step_light_configuration()

                return self.async_create_entry(title="", data=self.data)
        else:
            light = self.local_data["current_light"] = controlled_entities.pop(0)

        light = self.local_data["current_light"]
        state = self.hass.states.get(light)
        placeholders["light_name"] = state.name

        if user_input is None:
            # Load the previously configured list.
            brightness = (
                self.config_entry.options.get("entities", {})
                .get(light, {})
                .get("brightness", {})
            )

            brightness = "\n".join(
                [(str(key) + ": " + str(brightness[key])) for key in brightness]
            )
        else:
            brightness = user_input["brightness"]

        schema = {
            vol.Optional(
                "brightness", description={"suggested_value": brightness}
            ): selector({"template": {}})
        }

        return self.async_show_form(
            step_id="light_configuration",
            last_step=len(controlled_entities) == 0,
            data_schema=vol.Schema(schema),
            description_placeholders=placeholders,
            errors=errors,
        )
