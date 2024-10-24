# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path
import re
import sys

from dynaconf import Dynaconf
import ldap
from loguru import logger
import openstack
import typer
from typing_extensions import Annotated
from typing import Optional

# Default roles to be assigned to a new user for a project
DEFAULT_ROLES = ["member", "load-balancer_member"]


def get_settings(domain_name: str):
    # NOTE: This toxdir thing is super hacky, but works that way for us for now.
    toxdir = Path(__file__).parents[1]
    settings = Dynaconf(
        envvar_prefix="OPM",
        root_path=toxdir,
        settings_files=["settings.toml"],
        environments=True,
        env=domain_name,
    )
    return settings


def run(
    debug: Annotated[
        bool, typer.Option("--debug/--nodebug", help="Debug mode")
    ] = False,
    cloud_name: Annotated[
        str, typer.Option("--cloud", help="Cloud name in clouds.yml")
    ] = "admin",
    domain_name: Annotated[
        str, typer.Option("--domain", help="Domain to be managed")
    ] = "default",
    ldap_server: Annotated[
        Optional[str], typer.Option("--ldap-server", help="LDAP server URL")
    ] = None,
    ldap_username: Annotated[
        Optional[str], typer.Option("--ldap-username", help="LDAP username")
    ] = None,
    ldap_password: Annotated[
        Optional[str], typer.Option("--ldap-password", help="LDAP password")
    ] = None,
    ldap_base_dn: Annotated[
        Optional[str], typer.Option("--ldap-base-dn", help="LDAP base DN")
    ] = None,
    ldap_project_group_prefix: Annotated[
        Optional[str],
        typer.Option("--ldap-project-group-prefix", help="LDAP project group prefix"),
    ] = None,
    ldap_admin_group_cn: Annotated[
        Optional[str], typer.Option("--ldap-admin-group-cn", help="LDAP admin group CN")
    ] = None,
    ldap_object_class: Annotated[
        Optional[str], typer.Option("--ldap-object-class", help="LDAP object class")
    ] = None,
    ldap_search_attribute: Annotated[
        Optional[str],
        typer.Option("--ldap-search-attribute", help="LDAP search attribute"),
    ] = None,
) -> None:

    if debug:
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

    settings = get_settings(domain_name)

    # set ldap parameters

    ldap_base_dn = ldap_base_dn or settings.get("ldap_base_dn", None)
    ldap_admin_group_cn = ldap_admin_group_cn or settings.get(
        "ldap_admin_group_cn", None
    )
    ldap_project_group_prefix = ldap_project_group_prefix or settings.get(
        "ldap_project_group_prefix", None
    )
    ldap_object_class = ldap_object_class or settings.get("ldap_object_class", None)
    ldap_password = ldap_password or settings.get("ldap_password", None)
    ldap_search_attribute = ldap_search_attribute or settings.get(
        "ldap_search_attribute", None
    )
    ldap_server = ldap_server or settings.get("ldap_server", None)
    ldap_username = ldap_username or settings.get("ldap_username", None)

    # set project parameters

    # get ldap information

    conn = ldap.initialize(ldap_server)
    conn.simple_bind_s(ldap_username, ldap_password)

    # check openstack projects

    os_cloud = openstack.connect(cloud=cloud_name)
    domain = os_cloud.identity.find_domain(domain_name)

    # cache roles
    CACHE_ROLES = {}
    for role in os_cloud.identity.roles():
        CACHE_ROLES[role.name] = role

    # handle project groups
    search_filter = (
        f"(&(objectClass={ldap_object_class})(cn={ldap_project_group_prefix}*))"
    )
    result = conn.search_s(
        ldap_base_dn, ldap.SCOPE_SUBTREE, search_filter, [ldap_search_attribute]
    )

    for a, b in result:
        m = re.search(rf"cn={ldap_project_group_prefix}(\w+),", a)
        if m:
            project = os_cloud.identity.find_project(
                f"{domain.name}-{m.group(1)}", domain_id=domain.id
            )
            if not project:
                logger.warning(f"Create project {domain.name}-{m.group(1)} first")
            else:
                for x in b[ldap_search_attribute]:
                    username = x.decode("utf-8")

                    logger.debug(f"Checking user {username}")
                    user = os_cloud.identity.find_user(username, domain_id=domain.id)

                    if not user:
                        logger.warning(f"User {username} not found")
                        continue

                    logger.info(
                        f"{project.name} - ensure project permissions for user = {username}, user_id = {user.id}"
                    )
                    for role_name in DEFAULT_ROLES:
                        try:
                            role = CACHE_ROLES[role_name]
                            os_cloud.identity.assign_project_role_to_user(
                                project.id, user.id, role.id
                            )
                        except:
                            pass

    # handle the admin group
    search_filter = f"(&(objectClass={ldap_object_class})({ldap_admin_group_cn}))"
    result = conn.search_s(
        ldap_base_dn, ldap.SCOPE_SUBTREE, search_filter, [ldap_search_attribute]
    )

    for a, b in result:

        if a != f"{ldap_admin_group_cn},{ldap_base_dn}":
            continue

        for x in b[ldap_search_attribute]:
            username = x.decode("utf-8")

            logger.debug(f"Checking user {username}")
            user = os_cloud.identity.find_user(username, domain_id=domain.id)

            if not user:
                logger.warning(f"User {username} not found")
                continue

            for project in os_cloud.identity.projects(domain_id=domain.id):
                logger.info(
                    f"{project.name} - ensure admin project permissions for user = {username}, user_id = {user.id}"
                )
                for role_name in DEFAULT_ROLES:
                    try:
                        role = CACHE_ROLES[role_name]
                        os_cloud.identity.assign_project_role_to_user(
                            project.id, user.id, role.id
                        )
                    except:
                        pass

    conn.unbind_s()


def main() -> None:
    typer.run(run)


if __name__ == "__main__":
    main()
