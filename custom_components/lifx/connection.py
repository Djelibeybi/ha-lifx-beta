"""Custom connection class that closes and opens a connection for each request."""
from __future__ import annotations

import asyncio
from collections.abc import Callable

from aiolifx.aiolifx import UDP_BROADCAST_PORT, Light
from aiolifx.message import Message
import async_timeout

from .const import OVERALL_TIMEOUT, TARGET_ANY


class LIFXCustomConnection:
    """Manage a custom connection to a LIFX device."""

    def __init__(self, host, mac):
        """Init the connection."""
        self.host = host
        self.mac = mac
        self.device = None
        self.transport = None
        self._must_reconnect: bool = False
        self._inflight_limit = asyncio.Semaphore(4)

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
            # close the current connection
            self.async_stop()
            # then open a new one
            await self.async_setup()

        response: asyncio.Future[tuple[Light, Message]] = asyncio.Future()

        def _aiolifx_callback(light: Light, message: Message) -> None:
            """Process the response from aiolifx."""
            if (
                light.mac_addr == TARGET_ANY
                and message is not None
                and message.target_addr != TARGET_ANY
            ):
                light.mac_addr = message.target_addr

            if not response.done():
                response.set_result((light, message))

        message: Message = None

        async with self._inflight_limit:

            method(callb=_aiolifx_callback)
            async with async_timeout.timeout(delay=OVERALL_TIMEOUT):
                _, message = await response

            while len(self.device.message) > 0:
                await asyncio.sleep(0)

            if message is None:
                raise asyncio.TimeoutError("Timed out waiting for response.")

        return message

    def async_stop(self):
        """Close the transport."""
        if self.device is not None and isinstance(self.device.task, asyncio.Task):
            self.device.task.cancel()
            self.device.task = None

        if self.transport is not None and isinstance(self.transport, asyncio.Transport):
            self.transport.close()
            self.transport = None
