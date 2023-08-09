import random
import string
import sys

from oslo_config import cfg
import openstack
from tabulate import tabulate


# Default roles to be assigned to a new user for a project
DEFAULT_ROLES = ["creator", "member", "heat_stack_owner", "load-balancer_member"]

PROJECT_NAME = "openstack-user-manager"
CONF = cfg.CONF

# Available parameters for the CLI
opts = [
    cfg.BoolOpt("random", help="Generate random names", default=False),
    cfg.BoolOpt(
        "domain-name-prefix",
        help="Add domain name as prefix to the project name",
        default=True,
    ),
    cfg.IntOpt("password-length", help="Password length", default=16),
    cfg.StrOpt("cloud", help="Managed cloud", default="admin"),
    cfg.StrOpt("domain", help="Domain", default="default"),
    cfg.StrOpt("name", help="Username", default=""),
    cfg.StrOpt("project-name", help="Projectname", default=""),
    cfg.StrOpt("password", help="Password", default=None),
]
CONF.register_cli_opts(opts)

CONF(sys.argv[1:], project=PROJECT_NAME)


def generate_password(password_length: int) -> str:
    return "".join(
        random.choice(string.ascii_letters + string.digits)
        for x in range(password_length)
    )


# Connect to the OpenStack environment
conn = openstack.connect(cloud=CONF.cloud)

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

# Find or create the user
# FIXME(berendt): use get_project
if CONF.domain_name_prefix:
    project = conn.identity.find_project(
        f"{CONF.domain}-{CONF.project_name}", domain_id=domain.id
    )
else:
    project = conn.identity.find_project(CONF.project_name, domain_id=domain.id)

user = conn.identity.find_user(CONF.name, domain_id=domain.id)
if not user:
    user = conn.create_user(
        name=CONF.name,
        password=password,
        default_project=project,
        domain_id=domain.id,
    )
else:
    conn.update_user(user, password=password)

for role_name in DEFAULT_ROLES:
    try:
        role = conn.identity.find_role(role_name)
        conn.identity.assign_project_role_to_user(project.id, user.id, role.id)
    except:
        pass

result = [
    ["domain", CONF.domain, domain.id],
    ["project", CONF.project_name, project.id],
]

result.append(["user", CONF.name, user.id])
result.append(["password", password, ""])

print(tabulate(result, headers=["name", "value", "id"], tablefmt="psql"))
