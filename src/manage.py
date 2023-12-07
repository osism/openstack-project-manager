# SPDX-License-Identifier: AGPL-3.0-or-later

import math
import re
import sys

from deepmerge import always_merger
from loguru import logger
import neutronclient
import openstack
from oslo_config import cfg
import os_client_config
import yaml

PROJECT_NAME = "openstack-project-manager"
CONF = cfg.CONF
opts = [
    cfg.BoolOpt("assign-admin-user", help="Assign admin user", default=False),
    cfg.BoolOpt("dry-run", help="Do not really do anything", default=False),
    cfg.BoolOpt("manage-endpoints", help="Manage endpoints", default=False),
    cfg.BoolOpt("manage-homeprojects", help="Manage home projects", default=False),
    cfg.StrOpt("admin-domain", help="Admin domain", default="default"),
    cfg.StrOpt(
        "classes", help="Path to the classes.yml file", default="etc/classes.yml"
    ),
    cfg.StrOpt(
        "endpoints", help="Path to the endpoints.yml file", default="etc/endpoints.yml"
    ),
    cfg.StrOpt("cloud", help="Cloud name in clouds.yaml", default="admin"),
    cfg.StrOpt("domain", help="Domain to be managed"),
    cfg.StrOpt("name", help="Project to be managed"),
]
CONF.register_cli_opts(opts)
CONF(sys.argv[1:], project=PROJECT_NAME)

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


def get_quotaclass(quotaclass):
    with open(CONF.classes, "r") as fp:
        quotaclasses = yaml.load(fp, Loader=yaml.SafeLoader)

    if quotaclass not in quotaclasses:
        return None

    result = quotaclasses[quotaclass]

    if "parent" in result and result["parent"] in quotaclasses:
        return always_merger.merge(quotaclasses[result["parent"]], result)

    return result


def check_bool(project, param):
    return param in project and str(project.get(param)) in [
        "true",
        "True",
        "yes",
        "Yes",
    ]


def check_quota(project, cloud):
    if project.name == "service":
        quotaclass = get_quotaclass("service")
    elif project.name == "admin":
        quotaclass = get_quotaclass("admin")
    elif "quotaclass" in project:
        quotaclass = get_quotaclass(project.quotaclass)
    else:
        domain = cloud.get_domain(name_or_id=project.domain_id)
        if domain.name.startswith("ok"):
            quotaclass = get_quotaclass("okeanos")
        else:
            quotaclass = get_quotaclass("basic")

    logger.info(f"{project.name} - quotaclass {quotaclass}")

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

        if (
            "domain_name" != "default"
            and check_bool(project, "has_service_network")
            and not check_bool(project, "is_service_project")
        ):
            quota_router = quota_router + 1

    overwrites = {}

    # overwrite quotas
    for p in [x for x in project if x.startswith("quota_") and x != "quota_router"]:
        logger.info(f"{project.name} - overwriting {p[6:]} = {project.get(p)}")
        overwrites[p[6:]] = True
        if p[6:] in QUOTAS["network"]:
            quotaclass["network"][p[6:]] = int(project.get(p))
        elif p[6:] in QUOTAS["compute"]:
            quotaclass["compute"][p[6:]] = int(project.get(p))
        elif p[6:] in QUOTAS["volume"]:
            quotaclass["volume"][p[6:]] = int(project.get(p))

    logger.info(f"{project.name} - check network quota")
    quotanetwork = cloud.get_network_quotas(project.id)
    for key in quotaclass["network"]:
        if key == "router":
            quota_should_be = quota_router
        elif key in overwrites:
            quota_should_be = quotaclass["network"][key]
        else:
            quota_should_be = quotaclass["network"][key] * multiplier_network

        if quota_should_be != quotanetwork[key]:
            logger.info(
                f"{project.name} - network[{key}] = {quota_should_be} != {quotanetwork[key]}"
            )
            if not CONF.dry_run:
                cloud.set_network_quotas(project.id, **{key: quota_should_be})

    logger.info(f"{project.name} - check compute quota")
    quotacompute = cloud.get_compute_quotas(project.id)
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

        if quota_should_be != quotacompute[key]:
            logger.info(
                f"{project.name} - compute[{key}] = {quota_should_be} != {quotacompute[key]}"
            )
            if not CONF.dry_run:
                cloud.set_compute_quotas(project.id, **{key: quota_should_be})

    logger.info(f"{project.name} - check volume quota")
    quotavolume = cloud.get_volume_quotas(project.id)
    for key in quotaclass["volume"]:
        if key in ["per_volume_gigabytes"]:
            tmultiplier = 1
        else:
            tmultiplier = multiplier_storage

        if key in overwrites:
            quota_should_be = quotaclass["volume"][key]
        else:
            quota_should_be = quotaclass["volume"][key] * tmultiplier

        if quota_should_be != quotavolume[key]:
            logger.info(
                f"{project.name} - volume[{key}] = {quota_should_be} != {quotavolume[key]}"
            )
            if not CONF.dry_run:
                cloud.set_volume_quotas(project.id, **{key: quota_should_be})


def manage_external_network_rbacs(project, domain):
    if "quotaclass" in project:
        quotaclass = get_quotaclass(project.quotaclass)
    else:
        logger.warning(f"{project.name} - quotaclass not set --> use default")
        if domain.name.startswith("ok"):
            quotaclass = get_quotaclass("okeanos")
        else:
            quotaclass = get_quotaclass("basic")

    if (
        check_bool(project, "has_public_network")
        or check_bool(project, "show_public_network")
        or "public_network" in quotaclass
    ):
        if "public_network" in project:
            public_net_name = project.public_network
        else:
            public_net_name = "public"

        add_external_network(project, public_net_name)

    elif not check_bool(project, "show_public_network") and not check_bool(
        project, "has_public_network"
    ):
        if "public_network" in project:
            public_net_name = project.public_network
        else:
            public_net_name = "public"

        del_external_network(project, public_net_name)

    domain_name = domain.name.lower()

    if domain_name != "default" and check_bool(project, "has_service_network"):
        if "service_network" in project:
            public_net_name = project.service_network
        else:
            public_net_name = f"{domain_name}-service"

        # add_external_network(project, public_net_name)
        add_service_network(project, public_net_name)

    elif domain_name != "default" and not check_bool(project, "has_service_network"):
        if "service_network" in project:
            public_net_name = project.service_network
        else:
            public_net_name = f"{domain_name}-service"

        # del_external_network(project, public_net_name)
        del_service_network(project, public_net_name)


def check_volume_types(project, domain):
    if "quotaclass" in project:
        quotaclass = get_quotaclass(project.quotaclass)
    else:
        logger.warning(f"{project.name} - quotaclass not set --> use default")
        if domain.name.startswith("ok"):
            quotaclass = get_quotaclass("okeanos")
        else:
            quotaclass = get_quotaclass("basic")

    if "volume_types" in quotaclass:
        for item in quotaclass["volume_types"]:
            logger.info(f"{project.name} - add volume type {item}")
            volume_types = [
                x
                for x in cloud.block_storage.types(
                    **{"name": item, "is_public": "False"}
                )
            ]

            if len(volume_types) > 1:
                logger.error(
                    f"{project.name} - volume type {item} not unique, please use volume type ID"
                )
            elif len(volume_types) == 0:
                logger.error(f"{project.name} - volume type {item} not found")
            else:
                try:
                    cloud.block_storage.add_type_access(volume_types[0], project.id)
                except openstack.exceptions.ConflictException:
                    pass


def create_network_resources(project, domain):
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
                project,
                net_name,
                subnet_name,
                router_name,
                public_net_name,
                availability_zone,
            )

    if "domain_name" != "default" and check_bool(project, "has_service_network"):
        logger.info(f"{project.name} - check service network resources")

        if "service_network" in project:
            availability_zone = "nova"
            public_net_name = project.service_network
        else:
            availability_zone = "nova"
            public_net_name = f"{domain_name}-service"

        if check_bool(project, "is_service_project"):
            create_service_network(
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
                project,
                net_name,
                subnet_name,
                router_name,
                public_net_name,
                availability_zone,
            )


def add_service_network(project, net_name):
    if "service_network_type" in project:
        service_network_type = f"access_as_{project.service_network_type}"
    else:
        service_network_type = "access_as_shared"

    try:
        logger.info(
            f"{project.name} - check if service rbac policy must be created ({net_name})"
        )
        net = cloud.get_network(net_name)
        rbac_policies = neutron.list_rbac_policies(
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

        if not CONF.dry_run and len(rbac_policies["rbac_policies"]) == 0:
            logger.info(f"{project.name} - create service rbac policy ({net_name})")
            neutron.create_rbac_policy(
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


def del_service_network(project, public_net_name):
    try:
        logger.info(
            f"{project.name} - check if service rbac policy must be deleted ({public_net_name})"
        )

        public_net = cloud.get_network(public_net_name)
        rbac_policies = neutron.list_rbac_policies(
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

        if not CONF.dry_run and len(rbac_policies["rbac_policies"]) == 1:
            logger.info(
                f"{project.name} - delete service rbac policy ({public_net_name})"
            )
            rbac_policy = rbac_policies["rbac_policies"][0]["id"]
            neutron.delete_rbac_policy(rbac_policy)

    except neutronclient.common.exceptions.Conflict:
        pass
    except AttributeError:
        pass


def add_external_network(project, public_net_name):
    try:
        logger.info(
            f"{project.name} - check if external rbac policy must be created ({public_net_name})"
        )

        public_net = cloud.get_network(public_net_name)
        rbac_policies = neutron.list_rbac_policies(
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

        if not CONF.dry_run and len(rbac_policies["rbac_policies"]) == 0:
            logger.info(f"{project.name} - create rbac policy ({public_net_name})")
            neutron.create_rbac_policy(
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


def del_external_network(project, public_net_name):
    try:
        logger.info(
            f"{project.name} - check if external rbac policy must be deleted ({public_net_name})"
        )

        public_net = cloud.get_network(public_net_name)
        rbac_policies = neutron.list_rbac_policies(
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

        if not CONF.dry_run and len(rbac_policies["rbac_policies"]) == 1:
            logger.info(
                f"{project.name} - delete external rbac policy ({public_net_name})"
            )
            rbac_policy = rbac_policies["rbac_policies"][0]["id"]
            neutron.delete_rbac_policy(rbac_policy)

    except neutronclient.common.exceptions.Conflict:
        pass
    except AttributeError:
        pass


def create_service_network(
    project, net_name, subnet_name, availability_zone, subnet_cidr=None
):
    domain = cloud.get_domain(name_or_id=project.domain_id)
    project_service = cloud.get_project(name_or_id=f"{domain.name}-service")

    net = cloud.get_network(net_name, filters={"project_id": project_service.id})

    if not net:
        logger.info(f"{project.name} - create service network ({net_name})")

        if not CONF.dry_run:
            net = cloud.create_network(
                net_name,
                project_id=project_service.id,
                availability_zone_hints=[availability_zone],
            )

            # Add the network to the same project as shared so that ports can be created in it
            add_service_network(project_service, net_name)

    subnet = cloud.get_subnet(subnet_name, filters={"project_id": project_service.id})
    if not subnet:
        logger.info(f"{project.name} - create service subnet ({subnet_name})")

        if not CONF.dry_run:
            if subnet_cidr:
                subnet = cloud.create_subnet(
                    net.id,
                    tenant_id=project_service.id,
                    subnet_name=subnet_name,
                    cidr=subnet_cidr,
                    enable_dhcp=True,
                )
            else:
                subnet = cloud.create_subnet(
                    net.id,
                    tenant_id=project_service.id,
                    subnet_name=subnet_name,
                    use_default_subnetpool=True,
                    enable_dhcp=True,
                )


def create_network(project, net_name, subnet_name, availability_zone):
    attach = False
    net = cloud.get_network(net_name, filters={"project_id": project.id})

    if not net:
        logger.info(f"{project.name} - create network ({net_name})")

        if not CONF.dry_run:
            net = cloud.create_network(
                net_name,
                project_id=project.id,
                availability_zone_hints=[availability_zone],
            )

    subnet = cloud.get_subnet(subnet_name, filters={"project_id": project.id})
    if not subnet:
        logger.info(f"{project.name} - create subnet ({subnet_name})")

        if not CONF.dry_run:
            subnet = cloud.create_subnet(
                net.id,
                tenant_id=project.id,
                subnet_name=subnet_name,
                use_default_subnetpool=True,
                enable_dhcp=True,
            )
        attach = True

    return (attach, subnet)


def create_network_with_router(
    project, net_name, subnet_name, router_name, public_net_name, availability_zone
):
    attach_router = False
    router = cloud.get_router(router_name, filters={"project_id": project.id})

    if not router:
        public_network_id = cloud.get_network(public_net_name).id
        logger.info(f"{project.name} - create router ({router_name})")

        if not CONF.dry_run:
            router = cloud.create_router(
                name=router_name,
                ext_gateway_net_id=public_network_id,
                enable_snat=True,
                project_id=project.id,
                availability_zone_hints=[availability_zone],
            )
        attach_router = True

    attach_subnet, subnet = create_network(
        project, net_name, subnet_name, availability_zone
    )

    if attach_router or attach_subnet:
        logger.info(
            f"{project.name} - attach subnet ({subnet_name}) to router ({router_name})"
        )
        if not CONF.dry_run:
            cloud.add_router_interface(router, subnet_id=subnet.id)


def check_homeproject_permissions(project, domain):
    if "homeproject" in project and not check_bool(project["homeproject"]):
        return

    username = project.name[len(domain) :]
    user = cloud.identity.find_user(username, domain_id=domain.id)

    # try username without the -XXX postfix
    if not user:
        username = re.sub(r"(.*)-[^.]*$", "\\1", project.name[len(domain) :])
        user = cloud.identity.find_user(username, domain_id=domain.id)

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
            role = CACHE_ROLES[role_name]
            cloud.identity.assign_project_role_to_user(project.id, user.id, role.id)
        except:
            pass


def assign_admin_user(project, domain):
    admin_name = f"{domain.name}-admin"

    if admin_name in CACHE_ADMIN_USERS:
        admin_user = CACHE_ADMIN_USERS[admin_name]
    else:
        admin_user = cloud.identity.find_user(
            admin_name, domain_id=CACHE_ADMIN_DOMAIN.id
        )
        CACHE_ADMIN_USERS[admin_name] = admin_user

    try:
        role = CACHE_ROLES["member"]
        cloud.identity.assign_project_role_to_user(project.id, admin_user.id, role.id)
        logger.info(f"{project.name} - assign admin user {admin_name}")
    except:
        pass


def check_endpoints(project):
    if "endpoints" in project:
        endpoints = project.endpoints.split(",")
    else:
        endpoints = ["default", "orchestration"]

    existing_endpoint_groups = {x.name: x for x in KEYSTONE.endpoint_groups.list()}

    assigned_endpoint_groups = [
        x.name
        for x in KEYSTONE.endpoint_filter.list_endpoint_groups_for_project(
            project=project.id
        )
    ]

    for endpoint in [x for e in endpoints for x in ENDPOINTS[e]]:
        for interface in ["internal", "public"]:
            endpoint_group_name = f"{endpoint}-{interface}"

            if endpoint_group_name not in assigned_endpoint_groups:
                if not CONF.dry_run:
                    try:
                        endpoint_group = existing_endpoint_groups[endpoint_group_name]
                        KEYSTONE.endpoint_filter.add_endpoint_group_to_project(
                            endpoint_group=endpoint_group.id, project=project.id
                        )
                        logger.info(
                            f"{project.name} - add endpoint {endpoint} ({interface})"
                        )
                    except KeyError:
                        pass


def share_image_with_project(image, project):
    member = cloud.image.find_member(project.id, image.id)

    if not member:
        logger.info(f"{project.name} - add shared image '{image.name}'")
        member = cloud.image.add_member(image.id, member_id=project.id)

        if member.status != "accepted":
            cloud.image.update_member(member, image.id, status="accepted")


def share_images(project, domain):
    # get the images project
    project_images = cloud.get_project(name_or_id=f"{domain.name}-images")

    if project_images:
        # only images owned by the images project can be shared
        images = cloud.image.images(owner=project_images.id, visibility="shared")

        for image in images:
            share_image_with_project(image, project)


def cache_images(domain):
    # get the images project
    project_images = cloud.get_project(name_or_id=f"{domain.name}-images")

    if not project_images:
        logger.info(
            f"{domain.name} - image cache project {domain.name}-images not found, image cache feature not required"
        )
        return

    # only images owned by the images project should be cached
    images = cloud.image.images(owner=project_images.id, visibility="shared")

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
    volumes = cloud_domain_admin.volume.volumes(owner=project_images.id)
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

            cloud_domain_admin.volume.create_volume(
                name=volume_name, size=volume_size, imageRef=image.id
            )


def process_project(project, domain):
    logger.info(
        f"{project.name} - project_id = {project.id}, domain_id = {project.domain_id}"
    )

    if "unmanaged" in project:
        logger.warning(f"{project.name} - not managed --> skipping")
    else:
        domain = cloud.get_domain(project.domain_id)

        if "quotaclass" in project:
            quotaclass = project.quotaclass
        else:
            logger.warning(f"{project.name} - quotaclass not set --> use default")
            if domain.name.startswith("ok"):
                quotaclass = get_quotaclass("okeanos")
            else:
                quotaclass = get_quotaclass("basic")

        check_quota(project, cloud)

        if CONF.manage_endpoints:
            check_endpoints(project)

        if CONF.manage_homeprojects:
            check_homeproject_permissions(project, domain)

        if CONF.assign_admin_user:
            assign_admin_user(project, domain)

        manage_external_network_rbacs(project, domain)

        if check_bool(project, "has_shared_images"):
            share_images(project, domain)

        if (
            quotaclass not in ["default", "service"]
            and "managed_network_resources" in project
        ) or (
            check_bool(project, "is_service_project")
            and check_bool(project, "has_service_network")
        ):
            create_network_resources(project, domain)

        check_volume_types(project, domain)


# load configurations

with open(CONF.endpoints, "r") as fp:
    ENDPOINTS = yaml.load(fp, Loader=yaml.SafeLoader)

# get connections

cloud = openstack.connect(cloud=CONF.cloud)
KEYSTONE = os_client_config.make_client("identity", cloud=CONF.cloud)
neutron = os_client_config.make_client("network", cloud=CONF.cloud)

# cache roles
CACHE_ROLES = {}
for role in cloud.identity.roles():
    CACHE_ROLES[role.name] = role

# cache admin domain
if CONF.assign_admin_user:
    CACHE_ADMIN_DOMAIN = cloud.identity.find_domain(CONF.admin_domain)
    if not CACHE_ADMIN_DOMAIN:
        logger.error(f"admin domain {CONF.admin_domain} does not exist")
        sys.exit(1)

# cache admin users
CACHE_ADMIN_USERS: dict = {}

# check existence of project and/or domain

if CONF.name and not CONF.domain:
    project = cloud.get_project(name_or_id=CONF.name)
    if not project:
        logger.error(f"project {CONF.name} does not exist")
        sys.exit(1)

    if project.domain_id == "default" and CONF.name in UNMANAGED_PROJECTS:
        # the service project must always be able to access the public network.
        if CONF.name == "service":
            if "public_network" in project:
                public_net_name = project.public_network
            else:
                public_net_name = "public"
            add_external_network(project, public_net_name)

        # On the service and admin project, the quota is always managed as well.
        check_quota(project, cloud)

        logger.warning(f"project {CONF.name} in the default domain is not managed")
        sys.exit(0)

    domain = cloud.get_domain(name_or_id=project.domain_id)
    logger.info(f"{domain.name} - domain_id = {domain.id}")

    process_project(project, domain)

elif CONF.name and CONF.domain:
    domain = cloud.get_domain(name_or_id=CONF.domain)
    if not domain:
        logger.error(f"domain {CONF.domain} does not exist")
        sys.exit(1)

    if domain.id == "default" and CONF.name in UNMANAGED_PROJECTS:
        project = cloud.get_project(name_or_id=CONF.name, domain_id=domain.id)

        # the service project must always be able to access the public network.
        if CONF.name == "service":
            if "public_network" in project:
                public_net_name = project.public_network
            else:
                public_net_name = "public"
            add_external_network(project, public_net_name)

        # On the service and admin project, the quota is always managed as well.
        check_quota(project, cloud)

        logger.warning(f"project {CONF.name} in the default domain is not managed")
        sys.exit(0)

    logger.info(f"{domain.name} - domain_id = {domain.id}")

    project = cloud.get_project(name_or_id=CONF.name, domain_id=domain.id)
    if not project:
        logger.error(f"project {CONF.name} in domain {CONF.domain} does not exist")
        sys.exit(1)

    process_project(project, domain)

elif not CONF.name and CONF.domain:
    domain = cloud.get_domain(name_or_id=CONF.domain)
    if not domain:
        logger.error(f"domain {CONF.domain} does not exist")
        sys.exit(1)

    logger.info(f"{domain.name} - domain_id = {domain.id}")

    for project in cloud.list_projects(domain_id=domain.id):
        logger.info(f"{project.name} - project_id = {project.id}")
        if project.domain_id == "default" and project.name in UNMANAGED_PROJECTS:
            # the service project must always be able to access the public network.
            if project.name == "service":
                if "public_network" in project:
                    public_net_name = project.public_network
                else:
                    public_net_name = "public"
                add_external_network(project, public_net_name)

            # On the service and admin project, the quota is always managed as well.
            check_quota(project, cloud)

            logger.warning(
                f"project {project.name} in the default domain is not managed"
            )
        else:
            process_project(project, domain)

    cache_images(domain)

else:
    logger.info("Processing all domains")
    domains = cloud.list_domains()

    for domain in domains:
        logger.info(f"{domain.name} - domain_id = {domain.id}")

        for project in cloud.list_projects(domain_id=domain.id):
            logger.info(f"{project.name} - project_id = {project.id}")
            if project.domain_id == "default" and project.name in UNMANAGED_PROJECTS:
                # the service project must always be able to access the public network.
                if project.name == "service":
                    if "public_network" in project:
                        public_net_name = project.public_network
                    else:
                        public_net_name = "public"
                    add_external_network(project, public_net_name)
                logger.warning(
                    f"project {project.name} in the default domain is not managed"
                )

                # On the service and admin project, the quota is always managed as well.
                check_quota(project, cloud)
            else:
                process_project(project, domain)

        cache_images(domain)
