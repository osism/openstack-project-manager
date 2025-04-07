# SPDX-License-Identifier: AGPL-3.0-or-later

import math
import re
import sys

from deepmerge import always_merger
from loguru import logger
import neutronclient
import openstack
import os_client_config
import yaml
import typer
from typing import List, Optional, Tuple
from typing_extensions import Annotated

DEFAULT_ROLES = ["member", "load-balancer_member"]

UNMANAGED_PROJECTS = ["admin", "service"]

# all known quotas
QUOTAS = {
    "compute": [
        "cores",
        "injected_file_content_bytes",
        "injected_file_path_bytes",
        "injected_files",
        "instances",
        "key_pairs",
        "metadata_items",
        "ram",
        "server_group_members",
        "server_groups",
    ],
    "network": [
        "floatingip",
        "network",
        "port",
        "rbac_policy",
        "router",
        "security_group",
        "security_group_rule",
        "subnet",
        "subnetpool",
    ],
    "volume": [
        "backup_gigabytes",
        "backups",
        "gigabytes",
        "per_volume_gigabytes",
        "snapshots",
        "volumes",
    ],
}

logger_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>"
logger.remove()
logger.add(sys.stdout, format=logger_format)


class Configuration:

    def __init__(
        self,
        dry_run: bool,
        cloud_name: str,
        endpoints: str,
        assign_admin_user: bool,
        admin_domain: str,
    ):
        self.dry_run = dry_run

        # load configurations
        with open(endpoints, "r") as fp:
            self.ENDPOINTS = yaml.load(fp, Loader=yaml.SafeLoader)

        # get connections
        self.os_cloud = openstack.connect(cloud=cloud_name)
        self.os_keystone = os_client_config.make_client("identity", cloud=cloud_name)
        self.os_neutron = os_client_config.make_client("network", cloud=cloud_name)

        # cache roles
        self.CACHE_ROLES = {}
        for role in self.os_cloud.identity.roles():
            self.CACHE_ROLES[role.name] = role

        # cache admin domain
        self.assign_admin_user = assign_admin_user
        if self.assign_admin_user:
            self.CACHE_ADMIN_DOMAIN = self.os_cloud.identity.find_domain(admin_domain)
            if not self.CACHE_ADMIN_DOMAIN:
                logger.error(f"admin domain {admin_domain} does not exist")
                sys.exit(1)

        # cache admin users
        self.CACHE_ADMIN_USERS: dict = {}


def get_quotaclass(classes: str, quotaclass: str) -> Optional[dict]:
    with open(classes, "r") as fp:
        quotaclasses = yaml.load(fp, Loader=yaml.SafeLoader)

    if quotaclass not in quotaclasses:
        return None

    result = quotaclasses[quotaclass]

    if "parent" in result and result["parent"] in quotaclasses:
        return always_merger.merge(quotaclasses[result["parent"]], result)

    return result


def check_bool(project: openstack.identity.v3.project.Project, param: str) -> bool:
    return param in project and str(project.get(param)) in [
        "true",
        "True",
        "yes",
        "Yes",
    ]


def check_quota(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    classes: str,
) -> None:

    quotaclass_name = ""

    if project.name == "service":
        quotaclass_name = "service"
        quotaclass = get_quotaclass(classes, quotaclass_name)
    elif project.name == "admin":
        quotaclass_name = "admin"
        quotaclass = get_quotaclass(classes, quotaclass_name)
    elif "quotaclass" in project:
        quotaclass_name = project.quotaclass
        quotaclass = get_quotaclass(classes, quotaclass_name)
    else:
        domain = configuration.os_cloud.get_domain(name_or_id=project.domain_id)
        if domain.name.startswith("ok"):
            quotaclass_name = "okeanos"
            quotaclass = get_quotaclass(classes, quotaclass_name)
        else:
            quotaclass_name = "basic"
            quotaclass = get_quotaclass(classes, quotaclass_name)

    if quotaclass is None:
        logger.error(f"{classes} - does not contain the requested quotaclass")
        return

    logger.info(f"{project.name} - quotaclass {quotaclass_name}")

    if "quotamultiplier" in project:
        multiplier = int(project.quotamultiplier)
    else:
        multiplier = 1

    if "quotamultiplier_storage" in project:
        multiplier_storage = int(project.quotamultiplier_storage)
    else:
        multiplier_storage = multiplier

    if "quotamultiplier_compute" in project:
        multiplier_compute = int(project.quotamultiplier_compute)
    else:
        multiplier_compute = multiplier

    if "quotamultiplier_network" in project:
        multiplier_network = int(project.quotamultiplier_network)
    else:
        multiplier_network = multiplier

    if "quota_router" in project:
        quota_router = int(project.quota_router)
    else:
        quota_router = quotaclass["network"]["router"]

        if check_bool(project, "has_public_network") and not check_bool(
            project, "is_service_project"
        ):
            quota_router = quota_router + 1

        if check_bool(project, "has_service_network") and not check_bool(
            project, "is_service_project"
        ):
            quota_router = quota_router + 1

    overwrites = {}

    # overwrite quotas
    for p in [x for x in project if x.startswith("quota_") and x != "quota_router"]:
        logger.info(f"{project.name} - overwriting {p[6:]} = {project.get(p)}")
        overwrites[p[6:]] = True
        if p[6:] in QUOTAS["network"]:
            quotaclass["network"][p[6:]] = int(str(project.get(p)))
        elif p[6:] in QUOTAS["compute"]:
            quotaclass["compute"][p[6:]] = int(str(project.get(p)))
        elif p[6:] in QUOTAS["volume"]:
            quotaclass["volume"][p[6:]] = int(str(project.get(p)))

    logger.info(f"{project.name} - check network quota")
    quotanetwork = configuration.os_cloud.get_network_quotas(project.id)
    for key in quotaclass["network"]:
        if key == "router":
            quota_should_be = quota_router
        elif key in overwrites:
            quota_should_be = quotaclass["network"][key]
        else:
            quota_should_be = quotaclass["network"][key] * multiplier_network

        if quota_should_be < 0:
            quota_should_be = -1

        if quota_should_be != quotanetwork[key]:
            logger.info(
                f"{project.name} - network[{key}] = {quota_should_be} != {quotanetwork[key]}"
            )
            if not configuration.dry_run:
                configuration.os_cloud.set_network_quotas(
                    project.id, **{key: quota_should_be}
                )

    check_bandwidth_limit(configuration, project, quotaclass)

    logger.info(f"{project.name} - check compute quota")
    quotacompute = configuration.os_cloud.get_compute_quotas(project.id)
    for key in quotaclass["compute"]:
        if key in [
            "injected_file_content_bytes",
            "metadata_items",
            "injected_file_path_bytes",
        ]:
            tmultiplier = 1
        else:
            tmultiplier = multiplier_compute

        if key in overwrites:
            quota_should_be = quotaclass["compute"][key]
        else:
            quota_should_be = quotaclass["compute"][key] * tmultiplier

        if quota_should_be < 0:
            quota_should_be = -1

        if quota_should_be != quotacompute[key]:
            logger.info(
                f"{project.name} - compute[{key}] = {quota_should_be} != {quotacompute[key]}"
            )
            if not configuration.dry_run:
                configuration.os_cloud.set_compute_quotas(
                    project.id, **{key: quota_should_be}
                )

    logger.info(f"{project.name} - check volume quota")
    quotavolume = configuration.os_cloud.get_volume_quotas(project.id)
    for key in quotaclass["volume"]:
        if key in ["per_volume_gigabytes"]:
            tmultiplier = 1
        else:
            tmultiplier = multiplier_storage

        if key in overwrites:
            quota_should_be = quotaclass["volume"][key]
        else:
            quota_should_be = quotaclass["volume"][key] * tmultiplier

        if quota_should_be < 0:
            quota_should_be = -1

        if quota_should_be != quotavolume[key]:
            logger.info(
                f"{project.name} - volume[{key}] = {quota_should_be} != {quotavolume[key]}"
            )
            if not configuration.dry_run:
                configuration.os_cloud.set_volume_quotas(
                    project.id, **{key: quota_should_be}
                )


def update_bandwidth_policy_rule(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    policy: openstack.network.v2.qos_policy.QoSPolicy,
    direction: str,
    max_kbps: int,
    max_burst_kbps: int,
):
    existingRules = configuration.os_cloud.list_qos_bandwidth_limit_rules(
        policy.id, {"direction": direction}
    )
    existingRule = existingRules[0] if len(existingRules) > 0 else None

    if max_kbps == -1 and max_burst_kbps == -1:
        if existingRule:
            logger.info(f"{project.name} - removing {direction} bandwidth limit rule")
            configuration.os_cloud.delete_qos_bandwidth_limit_rule(
                policy.id, existingRule.id
            )
        return

    if not existingRule:
        logger.info(f"{project.name} - creating new {direction} bandwidth limit rule")
        configuration.os_cloud.create_qos_bandwidth_limit_rule(
            policy.id,
            max_kbps=max_kbps,
            max_burst_kbps=max_burst_kbps,
            direction=direction,
        )
    elif (
        existingRule.max_kbps != max_kbps
        or existingRule.max_burst_kbps != max_burst_kbps
    ):
        logger.info(f"{project.name} - updating {direction} bandwidth limit rule")
        configuration.os_cloud.update_qos_bandwidth_limit_rule(
            policy.id,
            existingRule.id,
            max_kbps=max_kbps,
            max_burst_kbps=max_burst_kbps,
        )


def check_bandwidth_limit(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    quotaclass: dict,
) -> None:

    domain = configuration.os_cloud.get_domain(name_or_id=project.domain_id)
    domain_name = domain.name.lower()

    if domain_name == "default" and project.name in ["admin", "service"]:
        logger.info(f"{project.name} - skip network bandwith limit policy check")
        return

    logger.info(f"{project.name} - check network bandwith limit policy")

    limit_egress = -1
    limit_egress_burst = -1
    limit_ingress = -1
    limit_ingress_burst = -1

    if "bandwidth" in quotaclass:
        if "egress" in quotaclass["bandwidth"]:
            limit_egress = int(quotaclass["bandwidth"]["egress"])
        if "egress_burst" in quotaclass["bandwidth"]:
            limit_egress_burst = int(quotaclass["bandwidth"]["egress_burst"])
        if "ingress" in quotaclass["bandwidth"]:
            limit_ingress = int(quotaclass["bandwidth"]["ingress"])
        if "ingress_burst" in quotaclass["bandwidth"]:
            limit_ingress_burst = int(quotaclass["bandwidth"]["ingress_burst"])

    existingPolicies = configuration.os_cloud.list_qos_policies(
        {"name": "bw-limiter", "project_id": project.id}
    )

    if (
        limit_egress == -1
        and limit_egress_burst == -1
        and limit_ingress == -1
        and limit_ingress_burst == -1
    ):
        # There are no limits defined (anymore) so we remove or skip the policy entirely
        if len(existingPolicies) > 0:
            logger.info(f"{project.name} - removing bandwidth limit policy")
            for policy in existingPolicies:
                configuration.os_cloud.delete_qos_policy(policy.id)
        return

    if len(existingPolicies) == 0:
        logger.info(f"{project.name} - creating new bandwidth limit policy")
        policy = configuration.os_cloud.create_qos_policy(
            name="bw-limiter", default=True, project_id=project.id
        )
    else:
        policy = existingPolicies[0]

    update_bandwidth_policy_rule(
        configuration, project, policy, "egress", limit_egress, limit_egress_burst
    )
    update_bandwidth_policy_rule(
        configuration, project, policy, "ingress", limit_ingress, limit_ingress_burst
    )


def manage_external_network_rbacs(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    domain: openstack.identity.v3.domain.Domain,
    classes: str,
) -> None:

    if "quotaclass" in project:
        quotaclass = get_quotaclass(classes, project.quotaclass)
    else:
        if domain.name.startswith("ok"):
            quotaclass = get_quotaclass(classes, "okeanos")
        else:
            quotaclass = get_quotaclass(classes, "basic")
        logger.warning(
            f"{project.name} - quotaclass not set --> use default of {quotaclass}"
        )

    if (
        check_bool(project, "has_public_network")
        or check_bool(project, "show_public_network")
        or (quotaclass and "public_network" in quotaclass)
    ):
        if "public_network" in project:
            public_net_name = project.public_network
        else:
            public_net_name = "public"

        add_external_network(configuration, project, public_net_name)

    elif not check_bool(project, "show_public_network") and not check_bool(
        project, "has_public_network"
    ):
        if "public_network" in project:
            public_net_name = project.public_network
        else:
            public_net_name = "public"

        del_external_network(configuration, project, public_net_name)

    domain_name = domain.name.lower()

    if domain_name != "default" and check_bool(project, "has_service_network"):
        if "service_network" in project:
            public_net_name = project.service_network
        else:
            public_net_name = f"{domain_name}-service"

        # add_external_network(configuration, project, public_net_name)
        add_service_network(configuration, project, public_net_name)

    elif domain_name != "default" and not check_bool(project, "has_service_network"):
        if "service_network" in project:
            public_net_name = project.service_network
        else:
            public_net_name = f"{domain_name}-service"

        # del_external_network(configuration, project, public_net_name)
        del_service_network(configuration, project, public_net_name)


def check_volume_types(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    domain: openstack.identity.v3.domain.Domain,
    classes: str,
) -> None:

    if "quotaclass" in project:
        quotaclass = get_quotaclass(classes, project.quotaclass)
    else:
        logger.warning(f"{project.name} - quotaclass not set --> use default")
        if domain.name.startswith("ok"):
            quotaclass = get_quotaclass(classes, "okeanos")
        else:
            quotaclass = get_quotaclass(classes, "basic")

    if quotaclass and "volume_types" in quotaclass:
        for item in quotaclass["volume_types"]:
            logger.info(f"{project.name} - add volume type {item}")
            volume_types = [
                x
                for x in configuration.os_cloud.block_storage.types(
                    **{"name": item, "is_public": "False"}
                )
            ]

            if len(volume_types) > 1:
                logger.error(
                    f"{project.name} - volume type {item} not unique, please use volume type ID"
                )
                continue

            if len(volume_types) == 0:
                logger.error(f"{project.name} - volume type {item} not found")
                continue

            try:
                configuration.os_cloud.block_storage.add_type_access(
                    volume_types[0], project.id
                )
            except openstack.exceptions.ConflictException:
                pass


def manage_private_volumetypes(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    domain: openstack.identity.v3.domain.Domain,
) -> None:
    admin_project = configuration.os_cloud.get_project(
        name_or_id="admin", domain_id="default"
    )

    if not admin_project or project.id == admin_project.id:
        return

    logger.info(
        f"{project.name} - managing private volume types for domain {domain.name}"
    )

    all_volume_types = list(configuration.os_cloud.block_storage.types(is_public=False))

    for volume_type in all_volume_types:
        if not volume_type.name.upper().startswith(f"{domain.name.upper()}-"):
            continue

        location = volume_type.location.project.id
        if location != admin_project.id:
            continue

        projects_with_access = [
            x["project_id"]
            for x in configuration.os_cloud.block_storage.get_type_access(volume_type)
        ]

        if project.id in projects_with_access:
            logger.debug(
                f"{project.name} - volume type {volume_type.name} is already assigned"
            )
            continue

        logger.info(f"{project.name} - Adding volume type {volume_type.name}")
        configuration.os_cloud.block_storage.add_type_access(volume_type, project.id)


def check_flavors(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    domain: openstack.identity.v3.domain.Domain,
    classes: str,
) -> None:

    if "quotaclass" in project:
        quotaclass = get_quotaclass(classes, project.quotaclass)
    else:
        logger.warning(f"{project.name} - quotaclass not set --> use default")
        if domain.name.startswith("ok"):
            quotaclass = get_quotaclass(classes, "okeanos")
        else:
            quotaclass = get_quotaclass(classes, "basic")

    if quotaclass and "flavors" in quotaclass:
        for item in quotaclass["flavors"]:
            logger.info(f"{project.name} - add flavor {item}")

            all_flavors = list(configuration.os_cloud.list_flavors())
            flavors = []

            for f in all_flavors:
                if f.is_public:
                    continue

                if f.name == item or f.id == item:
                    flavors.append(f)

            if len(flavors) > 1:
                logger.error(
                    f"{project.name} - flavor {item} not unique, please use flavor ID"
                )
                continue

            if len(flavors) == 0:
                logger.error(f"{project.name} - flavor {item} not found")
                continue

            try:
                configuration.os_cloud.add_flavor_access(flavors[0].id, project.id)
            except openstack.exceptions.ConflictException:
                pass


def manage_private_flavors(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    domain: openstack.identity.v3.domain.Domain,
) -> None:
    logger.info(f"{project.name} - managing private flavors for domain {domain.name}")

    all_flavors = list(configuration.os_cloud.list_flavors())

    for flavor in all_flavors:
        if not flavor.name.upper().startswith(f"{domain.name.upper()}-"):
            continue

        if flavor.is_public:
            continue

        projects_with_access = [
            x["tenant_id"] for x in configuration.os_cloud.list_flavor_access(flavor)
        ]

        if project.id in projects_with_access:
            logger.debug(f"{project.name} - flavor {flavor.name} is already assigned")
            continue

        logger.info(f"{project.name} - Adding flavor {flavor.name}")
        configuration.os_cloud.add_flavor_access(flavor.id, project.id)


def create_network_resources(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    domain: openstack.identity.v3.domain.Domain,
) -> None:

    if "quotamultiplier" in project:
        multiplier = int(project.quotamultiplier)
    else:
        multiplier = 1

    if "quotamultiplier_network" in project:
        multiplier_network = int(project.quotamultiplier_network)
    else:
        multiplier_network = multiplier

    if not multiplier_network:
        return

    domain_name = domain.name.lower()
    project_name = project.name.lower()

    if check_bool(project, "has_public_network"):
        logger.info(f"{project.name} - check public network resources")

        if "public_network" in project:
            availability_zone = "nova"
            public_net_name = project.public_network
        else:
            availability_zone = "nova"
            public_net_name = "public"

        if check_bool(project, "is_service_project"):
            logger.info(
                f"{project.name} - it's a service project, network resources are not created"
            )
        else:
            net_name = f"net-to-{public_net_name}-{project_name}"
            router_name = f"router-to-{public_net_name}-{project_name}"
            subnet_name = f"subnet-to-{public_net_name}-{project_name}"

            create_network_with_router(
                configuration,
                project,
                net_name,
                subnet_name,
                router_name,
                public_net_name,
                availability_zone,
            )

    if domain_name != "default" and check_bool(project, "has_service_network"):
        logger.info(f"{project.name} - check service network resources")

        if "service_network" in project:
            availability_zone = "nova"
            public_net_name = project.service_network
        else:
            availability_zone = "nova"
            public_net_name = f"{domain_name}-service"

        if check_bool(project, "is_service_project"):
            create_service_network(
                configuration,
                project,
                public_net_name,
                f"subnet-{public_net_name}",
                availability_zone,
                project.service_network_cidr,
            )
        else:
            net_name = f"net-to-{public_net_name}-{project_name}"
            router_name = f"router-to-{public_net_name}-{project_name}"
            subnet_name = f"subnet-to-{public_net_name}-{project_name}"

            create_network_with_router(
                configuration,
                project,
                net_name,
                subnet_name,
                router_name,
                public_net_name,
                availability_zone,
            )


def add_service_network(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    net_name: str,
) -> None:

    if "service_network_type" in project:
        service_network_type = f"access_as_{project.service_network_type}"
    else:
        service_network_type = "access_as_shared"

    try:
        logger.info(
            f"{project.name} - check if service rbac policy must be created ({net_name})"
        )
        net = configuration.os_cloud.get_network(net_name)
        rbac_policies = configuration.os_neutron.list_rbac_policies(
            **{
                "target_tenant": project.id,
                "action": service_network_type,
                "object_type": "network",
                "object_id": net.id,
                "fields": "id",
            }
        )

        if len(rbac_policies["rbac_policies"]) == 0:
            logger.info(
                f"{project.name} - service rbac policy has to be created ({net_name})"
            )

        if not configuration.dry_run and len(rbac_policies["rbac_policies"]) == 0:
            logger.info(f"{project.name} - create service rbac policy ({net_name})")
            configuration.os_neutron.create_rbac_policy(
                {
                    "rbac_policy": {
                        "target_tenant": project.id,
                        "action": service_network_type,
                        "object_type": "network",
                        "object_id": net.id,
                    }
                }
            )

    except neutronclient.common.exceptions.Conflict:
        pass
    except AttributeError:
        pass


def del_service_network(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    public_net_name: str,
) -> None:

    try:
        logger.info(
            f"{project.name} - check if service rbac policy must be deleted ({public_net_name})"
        )

        public_net = configuration.os_cloud.get_network(public_net_name)
        rbac_policies = configuration.os_neutron.list_rbac_policies(
            **{
                "target_tenant": project.id,
                "action": "access_as_shared",
                "object_type": "network",
                "object_id": public_net.id,
                "fields": "id",
            }
        )

        if len(rbac_policies["rbac_policies"]) == 1:
            logger.info(
                f"{project.name} - service rbac policy has to be deleted ({public_net_name})"
            )

        if not configuration.dry_run and len(rbac_policies["rbac_policies"]) == 1:
            logger.info(
                f"{project.name} - delete service rbac policy ({public_net_name})"
            )
            rbac_policy = rbac_policies["rbac_policies"][0]["id"]
            configuration.os_neutron.delete_rbac_policy(rbac_policy)

    except neutronclient.common.exceptions.Conflict:
        pass
    except AttributeError:
        pass


def add_external_network(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    public_net_name: str,
) -> None:

    try:
        logger.info(
            f"{project.name} - check if external rbac policy must be created ({public_net_name})"
        )

        public_net = configuration.os_cloud.get_network(public_net_name)
        rbac_policies = configuration.os_neutron.list_rbac_policies(
            **{
                "target_tenant": project.id,
                "action": "access_as_external",
                "object_type": "network",
                "object_id": public_net.id,
                "fields": "id",
            }
        )

        if len(rbac_policies["rbac_policies"]) == 0:
            logger.info(
                f"{project.name} - external rbac policy has to be created ({public_net_name})"
            )

        if not configuration.dry_run and len(rbac_policies["rbac_policies"]) == 0:
            logger.info(f"{project.name} - create rbac policy ({public_net_name})")
            configuration.os_neutron.create_rbac_policy(
                {
                    "rbac_policy": {
                        "target_tenant": project.id,
                        "action": "access_as_external",
                        "object_type": "network",
                        "object_id": public_net.id,
                    }
                }
            )

    except neutronclient.common.exceptions.Conflict:
        pass
    except AttributeError:
        pass


def del_external_network(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    public_net_name: str,
) -> None:

    try:
        logger.info(
            f"{project.name} - check if external rbac policy must be deleted ({public_net_name})"
        )

        public_net = configuration.os_cloud.get_network(public_net_name)
        rbac_policies = configuration.os_neutron.list_rbac_policies(
            **{
                "target_tenant": project.id,
                "action": "access_as_external",
                "object_type": "network",
                "object_id": public_net.id,
                "fields": "id",
            }
        )

        if len(rbac_policies["rbac_policies"]) == 1:
            logger.info(
                f"{project.name} - external rbac policy has to be deleted ({public_net_name})"
            )

        if not configuration.dry_run and len(rbac_policies["rbac_policies"]) == 1:
            logger.info(
                f"{project.name} - delete external rbac policy ({public_net_name})"
            )
            rbac_policy = rbac_policies["rbac_policies"][0]["id"]
            configuration.os_neutron.delete_rbac_policy(rbac_policy)

    except neutronclient.common.exceptions.Conflict:
        pass
    except AttributeError:
        pass


def create_service_network(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    net_name: str,
    subnet_name: str,
    availability_zone: str,
    subnet_cidr: Optional[str] = None,
) -> None:

    domain = configuration.os_cloud.get_domain(name_or_id=project.domain_id)
    project_service = configuration.os_cloud.get_project(
        name_or_id=f"{domain.name}-service"
    )

    net = configuration.os_cloud.get_network(
        net_name, filters={"project_id": project_service.id}
    )

    if not net:
        logger.info(f"{project.name} - create service network ({net_name})")

        if not configuration.dry_run:
            net = configuration.os_cloud.create_network(
                net_name,
                project_id=project_service.id,
                availability_zone_hints=[availability_zone],
            )

            # Add the network to the same project as shared so that ports can be created in it
            add_service_network(configuration, project_service, net_name)

    subnet = configuration.os_cloud.get_subnet(
        subnet_name, filters={"project_id": project_service.id}
    )

    if not subnet:
        logger.info(f"{project.name} - create service subnet ({subnet_name})")

        if not configuration.dry_run:
            if subnet_cidr:
                subnet = configuration.os_cloud.create_subnet(
                    net.id,
                    tenant_id=project_service.id,
                    subnet_name=subnet_name,
                    cidr=subnet_cidr,
                    enable_dhcp=True,
                )
            else:
                subnet = configuration.os_cloud.create_subnet(
                    net.id,
                    tenant_id=project_service.id,
                    subnet_name=subnet_name,
                    use_default_subnetpool=True,
                    enable_dhcp=True,
                )


def create_network(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    net_name: str,
    subnet_name: str,
    availability_zone: str,
) -> Tuple[bool, openstack.network.v2.subnet.Subnet]:

    attach = False
    net = configuration.os_cloud.get_network(
        net_name, filters={"project_id": project.id}
    )

    if not net:
        logger.info(f"{project.name} - create network ({net_name})")

        if not configuration.dry_run:
            net = configuration.os_cloud.create_network(
                net_name,
                project_id=project.id,
                availability_zone_hints=[availability_zone],
            )

    subnet = configuration.os_cloud.get_subnet(
        subnet_name, filters={"project_id": project.id}
    )

    if not subnet:
        logger.info(f"{project.name} - create subnet ({subnet_name})")

        if not configuration.dry_run:
            subnet = configuration.os_cloud.create_subnet(
                net.id,
                tenant_id=project.id,
                subnet_name=subnet_name,
                use_default_subnetpool=True,
                enable_dhcp=True,
            )
        attach = True

    return (attach, subnet)


def create_network_with_router(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    net_name: str,
    subnet_name: str,
    router_name: str,
    public_net_name: str,
    availability_zone: str,
) -> None:

    attach_router = False
    router = configuration.os_cloud.get_router(
        router_name, filters={"project_id": project.id}
    )

    if not router:
        public_network_id = configuration.os_cloud.get_network(public_net_name).id
        logger.info(f"{project.name} - create router ({router_name})")

        if not configuration.dry_run:
            router = configuration.os_cloud.create_router(
                name=router_name,
                ext_gateway_net_id=public_network_id,
                enable_snat=True,
                project_id=project.id,
                availability_zone_hints=[availability_zone],
            )
        attach_router = True

    attach_subnet, subnet = create_network(
        configuration, project, net_name, subnet_name, availability_zone
    )

    if attach_router or attach_subnet:
        logger.info(
            f"{project.name} - attach subnet ({subnet_name}) to router ({router_name})"
        )
        if not configuration.dry_run:
            configuration.os_cloud.add_router_interface(router, subnet_id=subnet.id)


def check_homeproject_permissions(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    domain: openstack.identity.v3.domain.Domain,
) -> None:

    if "homeproject" in project and not check_bool(project, "homeproject"):
        return

    username = project.name[len(domain.name) + 1 :]
    user = configuration.os_cloud.identity.find_user(username, domain_id=domain.id)

    # try username without the -XXX postfix
    if not user:
        username = re.sub(r"(.*)-[^.]*$", "\\1", project.name[len(domain.name) + 1 :])
        user = configuration.os_cloud.identity.find_user(username, domain_id=domain.id)

    # looks like there is no matching user for this project, nothing to do
    if not user:
        logger.info(
            f"{project.name} - no matching user found that can be assigned to this project as home project"
        )
        return

    logger.info(
        f"{project.name} - ensure home project permissions for user = {username}, user_id = {user.id}"
    )
    for role_name in DEFAULT_ROLES:
        try:
            role = configuration.CACHE_ROLES[role_name]
            configuration.os_cloud.identity.assign_project_role_to_user(
                project.id, user.id, role.id
            )
        except:
            pass


def assign_admin_user(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    domain: openstack.identity.v3.domain.Domain,
) -> None:

    admin_name = f"{domain.name}-admin"

    if admin_name in configuration.CACHE_ADMIN_USERS:
        admin_user = configuration.CACHE_ADMIN_USERS[admin_name]
    else:
        admin_user = configuration.os_cloud.identity.find_user(
            admin_name, domain_id=configuration.CACHE_ADMIN_DOMAIN.id
        )
        configuration.CACHE_ADMIN_USERS[admin_name] = admin_user

    try:
        role = configuration.CACHE_ROLES["member"]
        configuration.os_cloud.identity.assign_project_role_to_user(
            project.id, admin_user.id, role.id
        )
        logger.info(f"{project.name} - assign admin user {admin_name}")
    except:
        pass


def check_endpoints(
    configuration: Configuration, project: openstack.identity.v3.project.Project
) -> None:

    if "endpoints" in project:
        endpoints = project.endpoints.split(",")
    else:
        endpoints = ["default", "orchestration"]

    existing_endpoint_groups = {
        x.name: x for x in configuration.os_keystone.endpoint_groups.list()
    }

    assigned_endpoint_groups = [
        x.name
        for x in configuration.os_keystone.endpoint_filter.list_endpoint_groups_for_project(
            project=project.id
        )
    ]

    for endpoint in [x for e in endpoints for x in configuration.ENDPOINTS[e]]:
        for interface in ["internal", "public"]:
            endpoint_group_name = f"{endpoint}-{interface}"

            if endpoint_group_name in assigned_endpoint_groups:
                # Already assigned
                continue

            if configuration.dry_run:
                continue

            try:
                endpoint_group = existing_endpoint_groups[endpoint_group_name]
                configuration.os_keystone.endpoint_filter.add_endpoint_group_to_project(
                    endpoint_group=endpoint_group.id, project=project.id
                )
                logger.info(f"{project.name} - add endpoint {endpoint} ({interface})")
            except KeyError:
                pass


def share_image_with_project(
    configuration: Configuration,
    image: openstack.block_storage.v2.volume.Volume,
    project: openstack.identity.v3.project.Project,
) -> None:

    member = configuration.os_cloud.image.find_member(project.id, image.id)

    if member:
        return

    logger.info(f"{project.name} - add shared image '{image.name}'")
    member = configuration.os_cloud.image.add_member(image.id, member_id=project.id)

    if member.status != "accepted":
        configuration.os_cloud.image.update_member(member, image.id, status="accepted")


def share_images(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    domain: openstack.identity.v3.domain.Domain,
) -> None:

    # get the images project
    project_images = configuration.os_cloud.get_project(
        name_or_id=f"{domain.name}-images"
    )

    if not project_images:
        return

    # only images owned by the images project can be shared
    images = configuration.os_cloud.image.images(
        owner=project_images.id, visibility="shared"
    )

    for image in images:
        share_image_with_project(configuration, image, project)


def cache_images(
    configuration: Configuration, domain: openstack.identity.v3.domain.Domain
) -> None:

    # get the images project
    project_images = configuration.os_cloud.get_project(
        name_or_id=f"{domain.name}-images"
    )

    if not project_images:
        logger.info(
            f"{domain.name} - image cache project {domain.name}-images not found, image cache feature not required"
        )
        return

    # only images owned by the images project should be cached
    images = configuration.os_cloud.image.images(
        owner=project_images.id, visibility="shared"
    )

    try:
        cloud_domain_admin = openstack.connect(
            cloud=f"opm-{domain.name}-admin", project_name=project_images.name
        )
    except openstack.exceptions.ConfigException:
        logger.warning(
            f"{domain.name} - opm-{domain.name}-admin cloud profile not found, image cache feature not usable"
        )
        return

    # remove cache volume for which there is no image anymore
    volumes: List[openstack.block_storage.v2.volume.Volume] = (
        cloud_domain_admin.volume.volumes(owner=project_images.id)
    )

    for volume in volumes:
        image = cloud_domain_admin.image.find_image(name_or_id=volume.name[6:])
        if not image:
            logger.info(
                f"{domain.name} - remove cache volume {volume.name} for which there is no image anymore"
            )
            cloud_domain_admin.volume.delete_volume(volume)

    for image in images:
        volume_name = f"cache-{image.id}"
        volume = cloud_domain_admin.volume.find_volume(name_or_id=volume_name)

        if not volume:
            logger.info(
                f"{domain.name} - prepare image cache for '{image.name}' ({image.id})"
            )

            # convert bytes to gigabytes and always round up
            volume_size = math.ceil(image.size / (1024 * 1024 * 1024))
            if volume_size < image.min_disk:
                volume_size = image.min_disk

            try:
                cloud_domain_admin.volume.create_volume(
                    name=volume_name, size=volume_size, imageRef=image.id
                )
            except openstack.exceptions.HttpException as e:
                logger.error(f"{domain.name} - {e.message}")


def process_project(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    classes: str,
    manage_endpoints: bool,
    manage_homeprojects: bool,
    manage_privatevolumetypes: bool,
    manage_privateflavors: bool,
) -> None:

    logger.info(
        f"{project.name} - project_id = {project.id}, domain_id = {project.domain_id}"
    )

    if "unmanaged" in project:
        logger.warning(f"{project.name} - not managed --> skipping")
    else:
        domain = configuration.os_cloud.get_domain(project.domain_id)

        if "quotaclass" in project:
            quotaclass = project.quotaclass
        else:
            logger.warning(f"{project.name} - quotaclass not set --> use default")
            if domain.name.startswith("ok"):
                quotaclass = get_quotaclass(classes, "okeanos")
            else:
                quotaclass = get_quotaclass(classes, "basic")

        check_quota(configuration, project, classes)

        if manage_endpoints:
            check_endpoints(configuration, project)

        if manage_homeprojects:
            check_homeproject_permissions(configuration, project, domain)

        if configuration.assign_admin_user:
            assign_admin_user(configuration, project, domain)

        manage_external_network_rbacs(configuration, project, domain, classes)

        if check_bool(project, "has_shared_images"):
            share_images(configuration, project, domain)

        if (
            quotaclass not in ["default", "service"]
            and "managed_network_resources" in project
        ) or (
            check_bool(project, "is_service_project")
            and check_bool(project, "has_service_network")
        ):
            create_network_resources(configuration, project, domain)

        check_volume_types(configuration, project, domain, classes)

        if manage_privatevolumetypes:
            manage_private_volumetypes(configuration, project, domain)

        check_flavors(configuration, project, domain, classes)

        if manage_privateflavors:
            manage_private_flavors(configuration, project, domain)


def handle_unmanaged_project(
    configuration: Configuration,
    project: openstack.identity.v3.project.Project,
    classes: str,
) -> None:
    # the service project must always be able to access the public network.
    if project.name == "service":
        if "public_network" in project:
            public_net_name = project.public_network
        else:
            public_net_name = "public"
        add_external_network(configuration, project, public_net_name)

    # On the service and admin project, the quota is always managed as well.
    check_quota(configuration, project, classes)

    logger.warning(
        f"project {project.name} ({project.id}) in the default domain is not managed"
    )


def run(
    assign_admin_user: Annotated[
        bool,
        typer.Option(
            "--assign-admin-user/--noassign-admin-user", help="Assign admin user"
        ),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run/--nodry-run", help="Do not really do anything")
    ] = False,
    manage_endpoints: Annotated[
        bool,
        typer.Option(
            "--manage-endpoints/--nomanage-endpoints", help="Manage endpoints"
        ),
    ] = False,
    manage_homeprojects: Annotated[
        bool,
        typer.Option(
            "--manage-homeprojects/--nomanage-homeprojects", help="Manage home projects"
        ),
    ] = False,
    manage_privatevolumetypes: Annotated[
        bool,
        typer.Option(
            "--manage-privatevolumetypes/--nomanage-privatevolumetypes",
            help="Manage private volume types",
        ),
    ] = True,
    manage_privateflavors: Annotated[
        bool,
        typer.Option(
            "--manage-privateflavors/--nomanage-privateflavors",
            help="Manage private flavors",
        ),
    ] = True,
    admin_domain: Annotated[
        str, typer.Option("--admin-domain", help="Admin domain")
    ] = "default",
    classes: Annotated[
        str, typer.Option("--classes", help="Path to the classes.yml file")
    ] = "etc/classes.yml",
    endpoints: Annotated[
        str, typer.Option("--endpoints", help="Path to the endpoints.yml file")
    ] = "etc/endpoints.yml",
    cloud_name: Annotated[
        str, typer.Option("--cloud", help="Cloud name in clouds.yaml")
    ] = "admin",
    domain_name: Annotated[
        Optional[str], typer.Option("--domain", help="Domain to be managed")
    ] = None,
    project_name: Annotated[
        Optional[str], typer.Option("--name", help="Project to be managed")
    ] = None,
) -> None:

    configuration = Configuration(
        dry_run, cloud_name, endpoints, assign_admin_user, admin_domain
    )

    # check existence of project and/or domain

    if project_name and not domain_name:
        project = configuration.os_cloud.get_project(name_or_id=project_name)
        if not project:
            logger.error(f"project {project_name} does not exist")
            sys.exit(1)

        if project.domain_id == "default" and project_name in UNMANAGED_PROJECTS:
            handle_unmanaged_project(configuration, project, classes)
            sys.exit(0)

        domain = configuration.os_cloud.get_domain(name_or_id=project.domain_id)
        logger.info(f"{domain.name} - domain_id = {domain.id}")

        process_project(
            configuration,
            project,
            classes,
            manage_endpoints,
            manage_homeprojects,
            manage_privatevolumetypes,
            manage_privateflavors,
        )

    elif project_name and domain_name:
        domain = configuration.os_cloud.get_domain(name_or_id=domain_name)
        if not domain:
            logger.error(f"domain {domain_name} does not exist")
            sys.exit(1)

        if domain.id == "default" and project_name in UNMANAGED_PROJECTS:
            project = configuration.os_cloud.get_project(
                name_or_id=project_name, domain_id=domain.id
            )

            handle_unmanaged_project(configuration, project, classes)
            sys.exit(0)

        logger.info(f"{domain.name} - domain_id = {domain.id}")

        project = configuration.os_cloud.get_project(
            name_or_id=project_name, domain_id=domain.id
        )
        if not project:
            logger.error(
                f"project {project_name} in domain {domain_name} does not exist"
            )
            sys.exit(1)

        process_project(
            configuration,
            project,
            classes,
            manage_endpoints,
            manage_homeprojects,
            manage_privatevolumetypes,
            manage_privateflavors,
        )

    elif not project_name and domain_name:
        domain = configuration.os_cloud.get_domain(name_or_id=domain_name)
        if not domain:
            logger.error(f"domain {domain} does not exist")
            sys.exit(1)

        logger.info(f"{domain.name} - domain_id = {domain.id}")

        for project in configuration.os_cloud.list_projects(domain_id=domain.id):
            if project.domain_id == "default" and project.name in UNMANAGED_PROJECTS:
                handle_unmanaged_project(configuration, project, classes)
            else:
                process_project(
                    configuration,
                    project,
                    classes,
                    manage_endpoints,
                    manage_homeprojects,
                    manage_privatevolumetypes,
                    manage_privateflavors,
                )

        cache_images(configuration, domain)

    else:
        logger.info("Processing all domains")
        domains = configuration.os_cloud.list_domains()

        for domain in domains:
            logger.info(f"{domain.name} - domain_id = {domain.id}")

            for project in configuration.os_cloud.list_projects(domain_id=domain.id):
                logger.info(f"{project.name} - project_id = {project.id}")
                if (
                    project.domain_id == "default"
                    and project.name in UNMANAGED_PROJECTS
                ):
                    handle_unmanaged_project(configuration, project, classes)
                else:
                    process_project(
                        configuration,
                        project,
                        classes,
                        manage_endpoints,
                        manage_homeprojects,
                        manage_privatevolumetypes,
                        manage_privateflavors,
                    )

            cache_images(configuration, domain)


def main() -> None:
    typer.run(run)


if __name__ == "__main__":
    main()
