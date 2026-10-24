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
Who a connecting receiver is, for the handshake's duplicate checks
(jsonclient.process_handshake).

A new connection whose user name is already connected is either the same
receiver coming back (replace the old connection, or refuse the new one if
the old one is still live) or a different receiver that picked the same name
(rename it). Before this module, "the same receiver" meant "the same uuid",
and the new connection always replaced the old one. Two live clients with
one uuid then took turns kicking each other out every ~10 s forever, and
neither ever synced. Seen on 2026-10-23, ~90 handshakes a minute on one
shard:
  - seven unrelated stations named my_feeder_name, all sending the
    placeholder uuid XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX from
    sdr-enthusiasts/docker-adsb-ultrafeeder's sample .env;
  - stations running two MLAT clients towards this server, from one host
    or from two.
"""

import math

# How recently a connection must have sent something to count as live. A
# TCP client sends sync and mlat messages many times a second while it sees
# aircraft, and the server's heartbeat makes it answer at least every 30 s.
# A connection that is really gone (half-open after a network change) goes
# quiet at once, so 45 s tells the two apart.
LIVE_S = 45.0

# A refused duplicate retries this long after the old connection would stop
# counting as live (retry_after), so a client that only came back early gets
# in on its next try.
RETRY_MARGIN_S = 15.0

# Two receivers with the same name and no uuid closer than this are one
# receiver connected twice: two antennas this close would be useless to
# each other for MLAT anyway.
SAME_PLACE_M = 100.0


def is_placeholder_uuid(uuid):
    """True for a uuid string that can't identify anyone: empty, or only
    X's or zeros once dashes and spaces are gone. Deliberately narrow:
    malformed but unique uuids (a stray '<', a missing digit, unicode
    dashes; all seen live) still identify one receiver and are kept."""
    if not isinstance(uuid, str):
        return False
    digits = set(uuid.replace('-', '').replace(' ', '').lower())
    return not digits or digits <= {'x'} or digits <= {'0'}


def distance_m(llh_a, llh_b):
    """Great-circle distance in metres between two (lat, lon, alt)."""
    lat1, lon1 = math.radians(llh_a[0]), math.radians(llh_a[1])
    lat2, lon2 = math.radians(llh_b[0]), math.radians(llh_b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(min(1.0, math.sqrt(h)))


def same_receiver(existing_uuid, existing_llh, uuid, llh):
    """Whether a new connection with an already-connected user name is that
    same receiver. With a uuid on either side, the uuids decide. With none
    on both sides, the position does."""
    if uuid is not None or existing_uuid is not None:
        return uuid is not None and uuid == existing_uuid
    return distance_m(existing_llh, llh) <= SAME_PLACE_M


def is_live(last_message_time, now):
    """Whether a connection has sent anything in the last LIVE_S seconds."""
    return last_message_time is not None and now - last_message_time < LIVE_S


def retry_after(last_message_time, now):
    """Seconds a refused duplicate should wait before trying again: until the
    old connection would no longer count as live, plus RETRY_MARGIN_S.

    A mass reconnect (an mlat-proxy rollout) brings most clients back while
    the server still holds their old connection, quiet for a second or two.
    With a fixed 300 s retry they all stayed out for five minutes (2026-10-24
    01:33 UTC: 3,175 -> ~1,230 MLAT feeders for 4.5 min). Waiting out only the
    liveness window lets them back within a minute. A real second client of a
    live receiver is refused again on each try, at one cheap handshake a
    minute: the old connection is never touched."""
    if last_message_time is None:
        return RETRY_MARGIN_S
    return max(0.0, LIVE_S - (now - last_message_time)) + RETRY_MARGIN_S
