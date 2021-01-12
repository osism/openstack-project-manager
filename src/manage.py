import logging
import sys

import neutronclient
import openstack
from oslo_config import cfg
import os_client_config
import yaml

PROJECT_NAME = 'openstack-project-manager'
CONF = cfg.CONF
opts = [
    cfg.BoolOpt('dry-run', help='Do not really do anything', default=False),
    cfg.StrOpt('classes', help='Path to the classes.yml file', default='etc/classes.yml'),
    cfg.StrOpt('endpoints', help='Path to the endpoints.yml file', default='etc/endpoints.yml'),
    cfg.StrOpt('cloud', help='Cloud name in clouds.yaml', default='service'),
    cfg.StrOpt('domain', help='Domain to be managed'),
    cfg.StrOpt('name', help='Project to be managed'),
]
CONF.register_cli_opts(opts)
CONF(sys.argv[1:], project=PROJECT_NAME)

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')


def check_bool(project, param):
    return param in project and str(project.get(param)) in ["true", "True", "yes", "Yes"]


def check_quota(project, cloud):

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
        quota_router = quotaclasses[project.quotaclass]["network"]["router"]

        if (check_bool(project, "has_public_network") and
                not check_bool(project, "is_servivce_project")):
            quota_router = quota_router + 1

        if ("domain_name" != "default" and
                check_bool(project, "has_domain_network") and
                not check_bool(project, "is_servivce_project")):
            quota_router = quota_router + 1

    logging.info("%s - check network quota" % project.name)
    quotanetwork = cloud.get_network_quotas(project.id)
    for key in quotaclasses[project.quotaclass]["network"]:

        if key == "router":
            quota_should_be = quota_router
        else:
            quota_should_be = quotaclasses[project.quotaclass]["network"][key] * multiplier_network

        if quota_should_be != quotanetwork[key]:
            logging.info("%s - network[%s] = %d != %d" % (project.name, key, quota_should_be, quotanetwork[key]))
            if not CONF.dry_run:
                cloud.set_network_quotas(project.id, **{key: quota_should_be})

    logging.info("%s - check compute quota" % project.name)
    quotacompute = cloud.get_compute_quotas(project.id)
    for key in quotaclasses[project.quotaclass]["compute"]:
        if key in ["injected_file_content_bytes", "metadata_items", "injected_file_path_bytes"]:
            tmultiplier = 1
        else:
            tmultiplier = multiplier_compute

        quota_should_be = quotaclasses[project.quotaclass]["compute"][key] * tmultiplier
        if quota_should_be != quotacompute[key]:
            logging.info("%s - compute[%s] = %d != %d" % (project.name, key, quota_should_be, quotacompute[key]))
            if not CONF.dry_run:
                cloud.set_compute_quotas(project.id, **{key: quota_should_be})

    logging.info("%s - check volume quota" % project.name)
    quotavolume = cloud.get_volume_quotas(project.id)
    for key in quotaclasses[project.quotaclass]["volume"]:
        if key in ["per_volume_gigabytes"]:
            tmultiplier = 1
        else:
            tmultiplier = multiplier_storage

        quota_should_be = quotaclasses[project.quotaclass]["volume"][key] * tmultiplier
        if quota_should_be != quotavolume[key]:
            logging.info("%s - volume[%s] = %d != %d" % (project.name, key, quota_should_be, quotavolume[key]))
            if not CONF.dry_run:
                cloud.set_volume_quotas(project.id, **{key: quota_should_be})


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
        logging.info("%s - check public network resources" % project.name)

        if "public_network" in project:
            availability_zone = "south-2"
            public_net_name = project.public_network
        else:
            availability_zone = "south-1"
            public_net_name = "public"

        net_name = "net-to-%s-%s" % (public_net_name, project_name)
        router_name = "router-to-%s-%s" % (public_net_name, project_name)
        subnet_name = "subnet-to-%s-%s" % (public_net_name, project_name)

        add_external_network(project, public_net_name)

        if check_bool(project, "is_service_project"):
            logging.info("%s - it's a service project, network resources are not created" % project.name)
        else:
            create_network_with_router(project, net_name, subnet_name, router_name, public_net_name, availability_zone)

    if "domain_name" != "default" and check_bool(project, "has_domain_network"):
        logging.info("%s - check domain network resources" % project.name)

        if "domain_network" in project:
            availability_zone = "south-2"
            public_net_name = project.domain_network
        else:
            availability_zone = "south-1"
            public_net_name = "%s-public" % domain_name

        net_name = "net-to-%s-%s" % (public_net_name, project_name)
        router_name = "router-to-%s-%s" % (public_net_name, project_name)
        subnet_name = "subnet-to-%s-%s" % (public_net_name, project_name)

        add_external_network(project, public_net_name)

        if check_bool(project, "is_service_project"):
            logging.info("%s - it's a service project, network resources are not created" % project.name)
        else:
            create_network_with_router(project, net_name, subnet_name, router_name, public_net_name, availability_zone)

    if check_bool(project, "has_shared_router"):

        if "public_network" in project:
            availability_zone = "south-2"
            public_net_name = project.public_network
        else:
            availability_zone = "south-1"
            public_net_name = "public"

        net_name = "net-to-%s-%s" % (public_net_name, project_name)
        subnet_name = "subnet-to-%s-%s" % (public_net_name, project_name)

        if check_bool(project, "is_service_project"):
            logging.info("%s - it's a service project, network resources are not created" % project.name)
        else:
            create_service_network(project, net_name, subnet_name, availability_zone)
            add_service_network(project, net_name)

    if check_bool(project, "show_public_network"):

        if "public_network" in project:
            public_net_name = project.public_network
        else:
            public_net_name = "public"

        add_external_network(project, public_net_name)

    if not check_bool(project, "show_public_network") and not check_bool(project, "has_public_network"):

        if "public_network" in project:
            public_net_name = project.public_network
        else:
            public_net_name = "public"

        del_external_network(project, public_net_name)

    if not check_bool(project, "has_domain_network"):

        if "domain_network" in project:
            public_net_name = project.domain_network
        else:
            public_net_name = "%s-public" % domain_name

        del_external_network(project, public_net_name)


def add_service_network(project, net_name):

    try:
        logging.info("%s - check if service rbac policy must be created (%s)" % (project.name, net_name))
        net = cloud.get_network(net_name)
        rbac_policies = neutron.list_rbac_policies(**{
            'target_tenant': project.id,
            'action': 'access_as_shared',
            'object_type': 'network',
            'object_id': net.id,
            'fields': 'id'
        })

        if len(rbac_policies["rbac_policies"]) == 0:
            logging.info("%s - service rbac policy has to be created (%s)" % (project.name, net_name))

        if not CONF.dry_run and len(rbac_policies["rbac_policies"]) == 0:
            logging.info("%s - create service rbac policy (%s)" % (project.name, net_name))
            neutron.create_rbac_policy({'rbac_policy': {
                'target_tenant': project.id,
                'action': 'access_as_shared',
                'object_type': 'network',
                'object_id': net.id
            }})

    except neutronclient.common.exceptions.Conflict:
        pass
    except AttributeError:
        pass


def add_external_network(project, public_net_name):

    try:
        logging.info("%s - check if external rbac policy must be created (%s)" % (project.name, public_net_name))

        public_net = cloud.get_network(public_net_name)
        rbac_policies = neutron.list_rbac_policies(**{
            'target_tenant': project.id,
            'action': 'access_as_external',
            'object_type': 'network',
            'object_id': public_net.id,
            'fields': 'id'
        })

        if len(rbac_policies["rbac_policies"]) == 0:
            logging.info("%s - external rbac policy has to be created (%s)" % (project.name, public_net_name))

        if not CONF.dry_run and len(rbac_policies["rbac_policies"]) == 0:
            logging.info("%s - create rbac policy (%s)" % (project.name, public_net_name))
            neutron.create_rbac_policy({'rbac_policy': {
                'target_tenant': project.id,
                'action': 'access_as_external',
                'object_type': 'network',
                'object_id': public_net.id
            }})

    except neutronclient.common.exceptions.Conflict:
        pass
    except AttributeError:
        pass


def del_external_network(project, public_net_name):

    try:
        logging.info("%s - check if external rbac policy must be deleted (%s)" % (project.name, public_net_name))

        public_net = cloud.get_network(public_net_name)
        rbac_policies = neutron.list_rbac_policies(**{
            'target_tenant': project.id,
            'action': 'access_as_external',
            'object_type': 'network',
            'object_id': public_net.id,
            'fields': 'id'
        })

        if len(rbac_policies["rbac_policies"]) == 1:
            logging.info("%s - external rbac policy has to be deleted (%s)" % (project.name, public_net_name))

        if not CONF.dry_run and len(rbac_policies["rbac_policies"]) == 1:
            logging.info("%s - delete external rbac policy (%s)" % (project.name, public_net_name))
            rbac_policy = rbac_policies["rbac_policies"][0]["id"]
            neutron.delete_rbac_policy(rbac_policy)

    except neutronclient.common.exceptions.Conflict:
        pass
    except AttributeError:
        pass


def create_service_network(project, net_name, subnet_name, availability_zone):

    domain = cloud.get_domain(name_or_id=project.domain_id)
    project_service = cloud.get_project(name_or_id="service-%s" % domain.name)

    net = cloud.get_network(net_name, filters={"project_id": project_service.id})

    if not net:
        logging.info("%s - create service network (%s)" % (project.name, net_name))

        if not CONF.dry_run:
            net = cloud.create_network(net_name, project_id=project_service.id, availability_zone_hints=[availability_zone])

    subnet = cloud.get_subnet(subnet_name, filters={"project_id": project_service.id})
    if not subnet:
        logging.info("%s - create service subnet (%s)" % (project.name, subnet_name))

        if not CONF.dry_run:
            subnet = cloud.create_subnet(
                net.id,
                tenant_id=project_service.id,
                subnet_name=subnet_name,
                use_default_subnetpool=True,
                enable_dhcp=True
            )


def create_network(project, net_name, subnet_name, availability_zone):

    attach = False
    net = cloud.get_network(net_name, filters={"project_id": project.id})

    if not net:
        logging.info("%s - create network (%s)" % (project.name, net_name))

        if not CONF.dry_run:
            net = cloud.create_network(net_name, project_id=project.id, availability_zone_hints=[availability_zone])

    subnet = cloud.get_subnet(subnet_name, filters={"project_id": project.id})
    if not subnet:
        logging.info("%s - create subnet (%s)" % (project.name, subnet_name))

        if not CONF.dry_run:
            subnet = cloud.create_subnet(
                net.id,
                tenant_id=project.id,
                subnet_name=subnet_name,
                use_default_subnetpool=True,
                enable_dhcp=True
            )
        attach = True

    return (attach, subnet)


def create_network_with_router(project, net_name, subnet_name, router_name, public_net_name, availability_zone):

    attach_router = False
    router = cloud.get_router(router_name, filters={"project_id": project.id})

    if not router:
        public_network_id = cloud.get_network(public_net_name).id
        logging.info("%s - create router (%s)" % (project.name, router_name))

        if not CONF.dry_run:
            router = cloud.create_router(
                name=router_name,
                ext_gateway_net_id=public_network_id,
                enable_snat=True,
                project_id=project.id,
                availability_zone_hints=[availability_zone]
            )
        attach_router = True

    attach_subnet, subnet = create_network(project, net_name, subnet_name, availability_zone)

    if attach_router or attach_subnet:
        logging.info("%s - attach subnet (%s) to router (%s)" % (project.name, subnet_name, router_name))
        if not CONF.dry_run:
            cloud.add_router_interface(router, subnet_id=subnet.id)


def check_endpoints(project):

    if "endpoints" in project:
        endpoints = project.endpoints.split(",")
    else:
        endpoints = ["default", "orchestration"]

    assigned_endpoint_groups = [
        x.name for x in KEYSTONE.endpoint_filter.list_endpoint_groups_for_project(project=project.id)
    ]

    for endpoint in [x for e in endpoints for x in ENDPOINTS[e]]:

        if endpoint == "keystone":
            interfaces = ["internal", "public", "admin"]
        else:
            interfaces = ["internal", "public"]

        for interface in interfaces:
            endpoint_group_name = "%s-%s" % (endpoint, interface)

            if endpoint_group_name not in assigned_endpoint_groups:
                logging.info("%s - add endpoint %s (%s)" % (project.name, endpoint, interface))

                if not CONF.dry_run:
                    endpoint_group = existing_endpoint_groups[endpoint_group_name]
                    KEYSTONE.endpoint_filter.add_endpoint_group_to_project(
                        endpoint_group=endpoint_group.id,
                        project=project.id
                    )


def process_project(project):

    logging.info("%s - project_id = %s, domain_id = %s" % (project.name, project.id, project.domain_id))

    if "unmanaged" in project:
        logging.info("%s - not managed" % project.name)
    elif "quotaclass" not in project:
        logging.warning("%s - quotaclass not set" % project.name)
    elif project.quotaclass not in quotaclasses:
        logging.warning("%s - quotaclass %s not defined" % (project.name, project.quotaclass))
    else:
        check_quota(project, cloud)

        if project.quotaclass not in ["default", "service"] and "unmanaged_network_resources" not in project:
            domain = cloud.get_domain(project.domain_id)
            create_network_resources(project, domain)

        check_endpoints(project)


# check runtim parameters

if not CONF.name and not CONF.domain:
    logging.error("project name or domain (or both) required")
    sys.exit(1)

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
        logging.error("project %s does not exist" % CONF.name)
        sys.exit(1)

    if project.domain_id == "default":
        logging.error("projects in the default domain are not managed")
        sys.exit(1)

    domain = cloud.get_domain(name_or_id=project.domain_id)
    logging.info("%s - domain_id = %s" % (domain.name, domain.id))

    process_project(project)

if CONF.name and CONF.domain:
    domain = cloud.get_domain(name_or_id=CONF.domain)
    if not domain:
        logging.error("domain %s does not exist" % CONF.domain)
        sys.exit(1)

    if domain.id == "default":
        logging.error("projects in the default domain are not managed")
        sys.exit(1)

    logging.info("%s - domain_id = %s" % (domain.name, domain.id))

    project = cloud.get_project(name_or_id=CONF.name, domain_id=domain.id)
    if not project:
        logging.error("project %s in domain %s does not exist" % (CONF.name, CONF.domain))
        sys.exit(1)

    process_project(project)

if not CONF.name and CONF.domain:
    domain = cloud.get_domain(name_or_id=CONF.domain)
    if not domain:
        logging.error("domain %s does not exist" % CONF.domain)
        sys.exit(1)

    if domain.id == "default":
        logging.error("projects in the default domain are not managed")
        sys.exit(1)

    logging.info("%s - domain_id = %s" % (domain.name, domain.id))

    for project in cloud.list_projects(domain_id=domain.id):
        process_project(project)
