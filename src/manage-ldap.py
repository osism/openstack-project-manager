# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path
import sys

from dynaconf import Dynaconf
import ldap
from loguru import logger
import openstack
from oslo_config import cfg

PROJECT_NAME = "openstack-project-manager"
CONF = cfg.CONF
opts = [
    cfg.BoolOpt("debug", help="Debug mode", default=False),
    cfg.StrOpt("cloud", help="Cloud name in clouds.yml", default="admin"),
    cfg.StrOpt("domain", help="Domain to be managed", default="default"),
    cfg.StrOpt("ldap-server", help="LDAP server URL"),
    cfg.StrOpt("ldap-username", help="LDAP username"),
    cfg.StrOpt("ldap-password", help="LDAP password"),
    cfg.StrOpt("ldap-base-dn", help="LDAP base DN"),
    cfg.StrOpt("ldap-admin-group-cn", help="LDAP admin group CN"),
    cfg.StrOpt("ldap-object-class", help="LDAP object class"),
    cfg.StrOpt("ldap-search-attribute", help="LDAP search attribute"),
]
CONF.register_cli_opts(opts)
CONF(sys.argv[1:], project=PROJECT_NAME)

# Default roles to be assigned to a new user for a project
DEFAULT_ROLES = ["member", "load-balancer_member"]

if CONF.debug:
    level = "DEBUG"
    log_fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
        "<level>{message}</level>"
    )
else:
    level = "INFO"
    log_fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
        "<level>{message}</level>"
    )

logger.remove()
logger.add(sys.stderr, format=log_fmt, level=level, colorize=True)

# read configuration

# NOTE: This toxdir thing is super hacky, but works that way for us for now.
toxdir = Path(__file__).parents[1]
settings = Dynaconf(
    envvar_prefix="OPM",
    root_path=toxdir,
    settings_files=["settings.toml"],
    environments=True,
    env=CONF.domain,
)

# set ldap parameters

ldap_base_dn = CONF.ldap_base_dn or settings.get("ldap_base_dn", None)
ldap_admin_group_cn = CONF.ldap_admin_group_cn or settings.get(
    "ldap_admin_group_cn", None
)
ldap_object_class = CONF.ldap_object_class or settings.get("ldap_object_class", None)
ldap_password = CONF.ldap_password or settings.get("ldap_password", None)
ldap_search_attribute = CONF.ldap_search_attribute or settings.get(
    "ldap_search_attribute", None
)
ldap_server = CONF.ldap_server or settings.get("ldap_server", None)
ldap_username = CONF.ldap_username or settings.get("ldap_username", None)

# set project parameters

# get ldap information

conn = ldap.initialize(ldap_server)
conn.simple_bind_s(ldap_username, ldap_password)

search_filter = f"(&(objectClass={ldap_object_class})({ldap_admin_group_cn}))"
result = conn.search_s(
    ldap_base_dn, ldap.SCOPE_SUBTREE, search_filter, [ldap_search_attribute]
)

# check openstack projects

cloud = openstack.connect(cloud=CONF.cloud)
domain = cloud.identity.find_domain(CONF.domain)

# cache roles
CACHE_ROLES = {}
for role in cloud.identity.roles():
    CACHE_ROLES[role.name] = role

for a, b in result:
    if a == f"{ldap_admin_group_cn},{ldap_base_dn}":
        for x in b[ldap_search_attribute]:
            username = x.decode("utf-8")

            logger.debug(f"Checking user {username}")
            user = cloud.identity.find_user(username, domain_id=domain.id)

            if user:
                for project in cloud.identity.projects(domain_id=domain.id):
                    logger.info(
                        f"{project.name} - ensure admin project permissions for user = {username}, user_id = {user.id}"
                    )
                    for role_name in DEFAULT_ROLES:
                        try:
                            role = CACHE_ROLES[role_name]
                            cloud.identity.assign_project_role_to_user(
                                project.id, user.id, role.id
                            )
                        except:
                            pass

conn.unbind_s()
