# SPDX-License-Identifier: AGPL-3.0-or-later

"""Typed access to the OpenStack service proxies used by this project.

openstacksdk ships type annotations and types attributes like
``Connection.identity`` as a union of every API version it supports
(``identity.v2.Proxy | identity.v3.Proxy``). This project only ever talks to
the versions below, so the helpers narrow the proxies down to those. The casts
have no effect at runtime, the version of the proxy is picked by openstacksdk
based on the API version the cloud reports.
"""

from typing import cast

import openstack
from openstack.block_storage.v3 import _proxy as block_storage_v3
from openstack.identity.v3 import _proxy as identity_v3
from openstack.image.v2 import _proxy as image_v2


def identity_proxy(os_cloud: openstack.connection.Connection) -> identity_v3.Proxy:
    return cast(identity_v3.Proxy, os_cloud.identity)


def block_storage_proxy(
    os_cloud: openstack.connection.Connection,
) -> block_storage_v3.Proxy:
    return cast(block_storage_v3.Proxy, os_cloud.block_storage)


def image_proxy(os_cloud: openstack.connection.Connection) -> image_v2.Proxy:
    return cast(image_v2.Proxy, os_cloud.image)
