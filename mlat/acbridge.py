# -*- mode: python; indent-tabs-mode: nil -*-

# Part of mlat-server: a Mode S multilateration server
# Copyright (C) 2015  Oliver Jowett <oliver@mutability.co.uk>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Internal-only side channel for the Mode A/C bridge.

Lets an external process (the acbridge service) submit an mlat candidate
message "as" an already-connected receiver, identified by that receiver's
uuid - reusing its already-established position and clock sync state. This
adds no new Receiver object and no new sync peers: the marginal cost is
whatever mlattrack.py already does per candidate message, not a new O(N)
clocktrack participant.

Wire format: one JSON object per UDP datagram, no framing needed:
    {"uuid": "<receiver uuid, as sent at handshake>",
     "t": <float, receiver-local clock ticks, same units the receiver's own
          client would use for its "mlat" messages>,
     "m": "<hex-encoded raw message bytes>"}

Not authenticated beyond network-level isolation: this must only ever be
reachable from inside the cluster (no Kubernetes Service/Ingress exposes
this port), same posture as the existing readsb output ports. Malformed or
unrecognized datagrams are dropped silently; there is no reply channel.
"""

import asyncio
import logging
import time

import ujson

glogger = logging.getLogger("acbridge")

# Same staleness/health gate JsonClient.process_message applies before
# accepting a real client's own "mlat" message - a receiver whose own sync
# is currently bad or stale shouldn't have candidate data injected either.
MAX_SYNC_AGE = 20.0


class BridgeProtocol(asyncio.DatagramProtocol):
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.received = 0
        self.dropped_no_receiver = 0
        self.dropped_bad_sync = 0
        self.dropped_malformed = 0

    def datagram_received(self, data, addr):
        try:
            msg = ujson.loads(data)
            uuid = msg['uuid']
            t = float(msg['t'])
            m = bytes.fromhex(msg['m'])
        except (ValueError, KeyError, TypeError):
            self.dropped_malformed += 1
            return

        self.received += 1

        receiver = self.coordinator.uuid_index.get(uuid)
        if receiver is None or receiver.dead:
            self.dropped_no_receiver += 1
            return

        now = time.time()
        if receiver.bad_syncs > 0 or now - receiver.last_sync > MAX_SYNC_AGE:
            self.dropped_bad_sync += 1
            return

        self.coordinator.receiver_mlat(receiver, t, m, now)

    def error_received(self, exc):
        glogger.warning("acbridge: UDP error: {0}".format(exc))


class BridgeListener(object):
    """Subtask: matches the coordinator subtasks lifecycle (start/close/wait_closed)."""

    def __init__(self, host, port, coordinator):
        self.host = host if host else '127.0.0.1'
        self.port = port
        self.coordinator = coordinator
        self.loop = coordinator.loop
        self.transport = None
        self.protocol = None

    async def start(self):
        if not self.port:
            return

        dgram_coro = self.loop.create_datagram_endpoint(
            protocol_factory=lambda: BridgeProtocol(self.coordinator),
            local_addr=(self.host, self.port))
        self.transport, self.protocol = await dgram_coro
        glogger.warning("acbridge: listening on {0}:{1} (UDP, internal only)".format(self.host, self.port))

    def close(self):
        if self.transport:
            self.transport.abort()

    async def wait_closed(self):
        return
