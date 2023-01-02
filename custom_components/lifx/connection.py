"""Custom connection class that closes and opens a connection for each request."""
from __future__ import annotations

import asyncio
from collections.abc import Callable

from aiolifx.aiolifx import UDP_BROADCAST_PORT, Light
from aiolifx.message import Message
import async_timeout

from .const import _LOGGER, OVERALL_TIMEOUT, TARGET_ANY


class LIFXCustomConnection:
    """Manage a custom connection to a LIFX device."""

    def __init__(self, host, mac):
        """Init the connection."""
        self.host = host
        self.mac = mac
        self.device = None
        self.transport = None
        self._must_reconnect: bool = False

    async def async_setup(self):
        """Ensure we are connected."""
        loop = asyncio.get_running_loop()
        self.transport, self.device = await loop.create_datagram_endpoint(
            lambda: Light(loop, self.mac, self.host),
            remote_addr=(self.host, UDP_BROADCAST_PORT),
        )

    async def async_get(self, method: Callable) -> Message:
        """Call aiolifx methods asynchronously."""

        if self.transport is None or self._must_reconnect is True:
            _LOGGER.debug("Creating new connection to %s (%s)", self.host, self.mac)
            loop = asyncio.get_running_loop()
            self.transport, self.device = await loop.create_datagram_endpoint(
                lambda: Light(loop, self.mac, self.host),
                remote_addr=(self.host, UDP_BROADCAST_PORT),
            )
            self._must_reconnect = False

        response: asyncio.Future[tuple[Light, Message]] = asyncio.Future()

        def _aiolifx_callback(light: Light, message: Message) -> None:
            """Process the response from aiolifx."""
            if message is None and not response.done():
                _LOGGER.warning(
                    "Empty repy received from %s (%s)", light.label, light.ip_addr
                )
                response.set_result((light, None))

            if (
                light.mac_addr == TARGET_ANY
                and message is not None
                and message.target_addr != TARGET_ANY
            ):
                light.mac_addr = message.target_addr
                _LOGGER.debug(
                    "Set mac address of %s (%s) to %s",
                    light.label,
                    light.ip_addr,
                    light.mac_addr,
                )

            if not response.done():
                response.set_result((light, message))

        light: Light = None
        message: Message = None

        method(callb=_aiolifx_callback)
        async with async_timeout.timeout(delay=OVERALL_TIMEOUT):
            light, message = await response

        while len(self.device.message) > 0:
            await asyncio.sleep(0)

        if message is None:
            self.async_stop()
            self._must_reconnect = True
            _LOGGER.debug("Closed connection to %s (%s)", self.host, self.mac)
            raise asyncio.TimeoutError(
                f"No response from {light.label} ({light.ip_addr}"
            )

        return message

    def async_stop(self):
        """Close the transport."""
        assert self.transport is not None
        self.transport.close()
        self.transport = None
