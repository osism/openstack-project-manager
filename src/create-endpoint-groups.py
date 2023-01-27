import os

from loguru import logger
import os_client_config
import openstack
from tabulate import tabulate

CLOUD = os.environ.get("CLOUD", "admin")

conn = openstack.connect(cloud=CLOUD)
keystone = os_client_config.make_client("identity", cloud=CLOUD)

existing_endpoint_groups = {x.name: x for x in keystone.endpoint_groups.list()}

changed = False
for service in keystone.services.list():
    for interface in ["public", "internal"]:
        name = f"{service.name}-{interface}"
        if name not in existing_endpoint_groups.keys():
            changed = True
            logger.info(
                f"Create endpoint {interface} for service {service.name} ({service.id})"
            )
            payload = {
                "name": f"{service.name}-{interface}",
                "filters": {"interface": interface, "service_id": service.id},
            }
            keystone.endpoint_groups.create(**payload)

if changed:
    existing_endpoint_groups = {x.name: x for x in keystone.endpoint_groups.list()}

result = []
for endpoint_group in existing_endpoint_groups:
    result.append([endpoint_group, existing_endpoint_groups[endpoint_group].id])

print(
    tabulate(
        result, headers=["endpoint group name", "endpoint group id"], tablefmt="psql"
    )
)
