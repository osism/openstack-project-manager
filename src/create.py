import random
import string
import sys

from oslo_config import cfg
import os_client_config
import openstack
from tabulate import tabulate


# Default roles to be assigned to a new user for a project
DEFAULT_ROLES = ["creator", "member", "heat_stack_owner", "load-balancer_member"]

PROJECT_NAME = "openstack-project-manager"
CONF = cfg.CONF

# Available parameters for the CLI
opts = [
    cfg.BoolOpt("assign-admin-user", help="Assign admin user", default=True),
    cfg.BoolOpt("create-admin-user", help="Create admin user", default=True),
    cfg.BoolOpt("create-user", help="Create user", default=False),
    cfg.BoolOpt(
        "domain-name-prefix",
        help="Add domain name as prefix to the project name",
        default=True,
    ),
    cfg.BoolOpt(
        "has-service-network", help="Has service network infrastructure", default=False
    ),
    cfg.BoolOpt(
        "has-public-network", help="Has public network infrastructure", default=True
    ),
    cfg.BoolOpt("has-shared-images", help="Has shared images", default=True),
    cfg.BoolOpt("random", help="Generate random names", default=False),
    cfg.BoolOpt(
        "managed-network-resources",
        help="Manage the network resources",
        default=False,
    ),
    cfg.IntOpt("password-length", help="Password length", default=16),
    cfg.IntOpt("quota-multiplier", help="Quota multiplier", default="1"),
    cfg.IntOpt(
        "quota-multiplier-compute", help="Quota multiplier compute", default=None
    ),
    cfg.IntOpt(
        "quota-multiplier-network", help="Quota multiplier network", default=None
    ),
    cfg.IntOpt(
        "quota-multiplier-storage", help="Quota multiplier storage", default=None
    ),
    cfg.IntOpt("quota-router", help="Quota router", default=1),
    cfg.StrOpt("cloud", help="Managed cloud", default="admin"),
    cfg.StrOpt("domain", help="Domain", default="default"),
    cfg.StrOpt("internal-id", help="Internal ID", default=None),
    cfg.StrOpt("name", help="Projectname", default="sandbox"),
    cfg.StrOpt("owner", help="Owner of the project", default=""),
    cfg.StrOpt("password", help="Password", default=None),
    cfg.StrOpt("public-network", help="Public network", default="public"),
    cfg.StrOpt("quota-class", help="Quota class", default="basic"),
    cfg.StrOpt("service-network-cidr", help="Service network CIDR", default=""),
]
CONF.register_cli_opts(opts)

CONF(sys.argv[1:], project=PROJECT_NAME)


def generate_password(password_length: int) -> int:
    return "".join(
        random.choice(string.ascii_letters + string.digits)
        for x in range(password_length)
    )


# Connect to the OpenStack environment
conn = openstack.connect(cloud=CONF.cloud)

# Generate a random name in the form abcd-0123
if CONF.random:
    part1 = "".join(random.choice(string.ascii_letters) for x in range(4)).lower()
    part2 = f"{random.randint(0,9999):04d}"
    name = f"{part1}-{part2}"
else:
    name = CONF.name

# Add the domain name as a prefix to the name
if CONF.domain_name_prefix:
    name = f"{CONF.domain}-{name}"

# Generate a random password from all ASCII characters + digits
if not CONF.password:
    password = generate_password(CONF.password_length)
else:
    password = CONF.password

# Establish dedicated connection to Keystone service
# FIXME(berendt): use get_domain
domain = conn.identity.find_domain(CONF.domain)
if not domain:
    domain = conn.create_domain(name=CONF.domain)

# Find or create the project
# FIXME(berendt): use get_project
project = conn.identity.find_project(name, domain_id=domain.id)
if not project:
    project = conn.create_project(name=name, domain_id=domain.id)

# FIXME(berendt): use openstacksdk
keystone = os_client_config.make_client("identity", cloud=CONF.cloud)

# Set the quota parameters of the project
keystone.projects.update(project=project.id, quotaclass=CONF.quota_class)
keystone.projects.update(project=project.id, quotamultiplier=CONF.quota_multiplier)
if CONF.quota_multiplier_compute:
    keystone.projects.update(
        project=project.id, quotamultiplier_compute=CONF.quota_multiplier_compute
    )
if CONF.quota_multiplier_network:
    keystone.projects.update(
        project=project.id, quotamultiplier_network=CONF.quota_multiplier_network
    )
if CONF.quota_multiplier_storage:
    keystone.projects.update(
        project=project.id, quotamultiplier_storage=CONF.quota_multiplier_storage
    )
if CONF.quota_router:
    keystone.projects.update(project=project.id, quota_router=CONF.quota_router)

# Set network parameters of the project
keystone.projects.update(
    project=project.id, has_service_network=str(CONF.has_service_network)
)
keystone.projects.update(
    project=project.id, service_network_cidr=str(CONF.service_network_cidr)
)
keystone.projects.update(
    project=project.id, has_public_network=str(CONF.has_public_network)
)
keystone.projects.update(
    project=project.id,
    show_public_network=str(CONF.has_public_network),
)
keystone.projects.update(project=project.id, public_network=CONF.public_network)

if CONF.name == "service":
    # Tag service projects
    keystone.projects.update(project=project.id, is_service_project=str(True))

    # For a service project always use the quota class service
    keystone.projects.update(project=project.id, quotaclass="service")

if CONF.name == "images":
    # For an images project always use the quota class default
    keystone.projects.update(project=project.id, quotaclass="images")
    keystone.projects.update(project=project.id, quota_router=0)
    # Only non-images projects can have shared images
    keystone.projects.update(project=project.id, has_shared_images=str(False))
    keystone.projects.update(project=project.id, has_public_network=str(False))
    keystone.projects.update(
        project=project.id,
        show_public_network=str(False),
    )
else:
    keystone.projects.update(
        project=project.id, has_shared_images=str(CONF.has_shared_images)
    )

# Set other parameters of the project
keystone.projects.update(project=project.id, owner=CONF.owner)

# The network resources of the project should be created automatically
if CONF.managed_network_resources:
    keystone.projects.update(project=project.id, managed_network_resources="True")

if CONF.internal_id:
    keystone.projects.update(project=project.id, internal_id=CONF.internal_id)

# Find or create the user of the project and assign the default roles
if CONF.create_user:
    user = conn.identity.find_user(name, domain_id=domain.id)
    if not user:
        user = conn.create_user(
            name=name,
            password=password,
            default_project=project,
            domain_id=domain.id,
            email=CONF.owner,
        )
    else:
        conn.update_user(user, password=password)

    for role_name in DEFAULT_ROLES:
        try:
            role = conn.identity.find_role(role_name)
            conn.identity.assign_project_role_to_user(project.id, user.id, role.id)
        except:
            pass

# Assign the domain admin user to the project
admin_password = None
admin_name = f"{CONF.domain}-admin"

# Admin users for a domain are always created in the default domain
admin_domain_id = "default"

if CONF.assign_admin_user:
    admin_user = conn.identity.find_user(admin_name, domain_id=admin_domain_id)

    if not admin_user and CONF.create_admin_user:
        admin_password = generate_password(CONF.password_length)
        admin_user = conn.create_user(
            name=admin_name, password=admin_password, domain_id=admin_domain_id
        )

    if admin_user:
        for role_name in DEFAULT_ROLES:
            try:
                role = conn.identity.find_role(role_name)
                conn.identity.assign_project_role_to_user(
                    project.id, admin_user.id, role.id
                )
            except:
                pass

result = [
    ["domain", CONF.domain, domain.id],
    ["project", name, project.id],
]

# Outputs details about the domain admin user
if CONF.create_admin_user and admin_password:
    result.append(["admin", admin_name, admin_user.id])
    result.append(["admin_password", admin_password, ""])

# Outputs details about the project user
if CONF.create_user:
    result.append(["user", name, user.id])
    result.append(["password", password, ""])

print(tabulate(result, headers=["name", "value", "id"], tablefmt="psql"))
