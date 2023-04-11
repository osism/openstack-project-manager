import math
import sys

from loguru import logger
import neutronclient
import openstack
from oslo_config import cfg
import os_client_config
import yaml

PROJECT_NAME = "openstack-project-manager"
CONF = cfg.CONF
opts = [
    cfg.BoolOpt("dry-run", help="Do not really do anything", default=False),
    cfg.BoolOpt("manage-endpoints", help="Manage endpoints", default=False),
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

UNMANAGED_PROJECTS = ["admin", "service"]

logger_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>"
logger.remove()
logger.add(sys.stdout, format=logger_format)


def check_bool(project, param):
    return param in project and str(project.get(param)) in [
        "true",
        "True",
        "yes",
        "Yes",
    ]


def check_quota(project, cloud):

    if project.name == "service":
        quotaclass = "service"
    elif project.name == "admin":
        quotaclass = "admin"
    else:
        quotaclass = project.quotaclass

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
        quota_router = quotaclasses[quotaclass]["network"]["router"]

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

    logger.info(f"{project.name} - check network quota")
    quotanetwork = cloud.get_network_quotas(project.id)
    for key in quotaclasses[quotaclass]["network"]:

        if key == "router":
            quota_should_be = quota_router
        else:
            quota_should_be = (
                quotaclasses[quotaclass]["network"][key] * multiplier_network
            )

        if quota_should_be != quotanetwork[key]:
            logger.info(
                f"{project.name} - network[{key} = {quota_should_be} != {quotanetwork[key]}"
            )
            if not CONF.dry_run:
                cloud.set_network_quotas(project.id, **{key: quota_should_be})

    logger.info(f"{project.name} - check compute quota")
    quotacompute = cloud.get_compute_quotas(project.id)
    for key in quotaclasses[quotaclass]["compute"]:
        if key in [
            "injected_file_content_bytes",
            "metadata_items",
            "injected_file_path_bytes",
        ]:
            tmultiplier = 1
        else:
            tmultiplier = multiplier_compute

        quota_should_be = quotaclasses[quotaclass]["compute"][key] * tmultiplier
        if quota_should_be != quotacompute[key]:
            logger.info(
                f"{project.name} - compute[{key}] = {quota_should_be} != {quotacompute[key]}"
            )
            if not CONF.dry_run:
                cloud.set_compute_quotas(project.id, **{key: quota_should_be})

    logger.info(f"{project.name} - check volume quota")
    quotavolume = cloud.get_volume_quotas(project.id)
    for key in quotaclasses[quotaclass]["volume"]:
        if key in ["per_volume_gigabytes"]:
            tmultiplier = 1
        else:
            tmultiplier = multiplier_storage

        quota_should_be = quotaclasses[quotaclass]["volume"][key] * tmultiplier
        if quota_should_be != quotavolume[key]:
            logger.info(
                f"{project.name} - volume[{key}] = {quota_should_be} != {quotavolume[key]}"
            )
            if not CONF.dry_run:
                cloud.set_volume_quotas(project.id, **{key: quota_should_be})


def manage_external_network_rbacs(project, domain):
    if check_bool(project, "has_public_network") or check_bool(
        project, "show_public_network"
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

    try:
        logger.info(
            f"{project.name} - check if service rbac policy must be created ({net_name})"
        )
        net = cloud.get_network(net_name)
        rbac_policies = neutron.list_rbac_policies(
            **{
                "target_tenant": project.id,
                "action": "access_as_shared",
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
                        "action": "access_as_shared",
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


def check_endpoints(project):

    if "endpoints" in project:
        endpoints = project.endpoints.split(",")
    else:
        endpoints = ["default", "orchestration"]

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

    if project_images:
        # only images owned by the images project should be cached
        images = cloud.image.images(owner=project_images.id, visibility="shared")

        cloud_domain_admin = openstack.connect(
            cloud=f"opm-{domain.name}-admin", project_name=project_images.name
        )

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


def process_project(project):

    logger.info(
        f"{project.name} - project_id = {project.id}, domain_id = {project.domain_id}"
    )

    if "unmanaged" in project:
        logger.warning(f"{project.name} - not managed --> skipping")
    elif "quotaclass" not in project:
        logger.warning(f"{project.name} - quotaclass not set --> skipping")
    elif project.quotaclass not in quotaclasses:
        logger.warning(
            f"{project.name} - quotaclass {project.quotaclass} not defined --> skipping"
        )
    else:
        domain = cloud.get_domain(project.domain_id)

        check_quota(project, cloud)

        if CONF.manage_endpoints:
            check_endpoints(project)
        manage_external_network_rbacs(project, domain)

        if check_bool(project, "has_shared_images"):
            share_images(project, domain)

        if (
            project.quotaclass not in ["default", "service"]
            and "managed_network_resources" in project
        ) or (
            check_bool(project, "is_service_project")
            and check_bool(project, "has_service_network")
        ):
            create_network_resources(project, domain)


# load configurations

with open(CONF.classes, "r") as fp:
    quotaclasses = yaml.load(fp, Loader=yaml.SafeLoader)

with open(CONF.endpoints, "r") as fp:
    ENDPOINTS = yaml.load(fp, Loader=yaml.SafeLoader)

# get connections

cloud = openstack.connect(cloud=CONF.cloud)
KEYSTONE = os_client_config.make_client("identity", cloud=CONF.cloud)
neutron = os_client_config.make_client("network", cloud=CONF.cloud)

# get data

existing_endpoint_groups = {x.name: x for x in KEYSTONE.endpoint_groups.list()}

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

    process_project(project)

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

    process_project(project)

elif not CONF.name and CONF.domain:
    domain = cloud.get_domain(name_or_id=CONF.domain)
    if not domain:
        logger.error(f"domain {CONF.domain} does not exist")
        sys.exit(1)

    logger.info(f"{domain.name} - domain_id = {domain.id}")

    for project in cloud.list_projects(domain_id=domain.id):
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
            process_project(project)

    cache_images(domain)

else:
    logger.info("Processing all domains")
    domains = cloud.list_domains()

    for domain in domains:
        logger.info(f"{domain.name} - domain_id = {domain.id}")

        for project in cloud.list_projects(domain_id=domain.id):
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
                process_project(project)

        cache_images(domain)
