import os
import sys

import keystoneauth1
import os_client_config
import shade
from tabulate import tabulate
import yaml

CLOUDNAME = os.environ.get("CLOUD", "service")

cloud = shade.operator_cloud(cloud=CLOUDNAME)
keystone = os_client_config.make_client("identity", cloud=CLOUDNAME)

existing_endpoint_groups = {x.name: x for x in keystone.endpoint_groups.list()}

changed = False
for service in keystone.services.list():
    for interface in ["public", "internal", "admin"]:
        name = "%s-%s" % (service.name, interface)
        if name not in existing_endpoint_groups.keys():
            changed = True
            print("create endpoint %s for service %s (%s)" % (interface, service.name, service.id))
            payload = {
                "name": "%s-%s" % (service.name, interface),
                "filters": {
                    "interface": interface,
                    "service_id": service.id
                }
            }
            keystone.endpoint_groups.create(**payload)

if changed:
    existing_endpoint_groups = {x.name: x for x in keystone.endpoint_groups.list()}

result = []
for endpoint_group in existing_endpoint_groups:
    result.append([endpoint_group, existing_endpoint_groups[endpoint_group].id])

print(tabulate(result, headers=["endpoint group name", "endpoint group id"], tablefmt="psql"))
