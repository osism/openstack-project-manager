# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path
import subprocess
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
    ldap_group_cn: Annotated[
        Optional[str], typer.Option("--ldap-group-cn", help="LDAP group CN")
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
    toxdir = Path(__file__).parents[1]
    settings = get_settings(domain_name)

    # set ldap parameters

    ldap_base_dn = ldap_base_dn or settings.get("ldap_base_dn", None)
    ldap_group_cn = ldap_group_cn or settings.get("ldap_group_cn", None)
    ldap_object_class = ldap_object_class or settings.get("ldap_object_class", None)
    ldap_password = ldap_password or settings.get("ldap_password", None)
    ldap_search_attribute = ldap_search_attribute or settings.get(
        "ldap_search_attribute", None
    )
    ldap_server = ldap_server or settings.get("ldap_server", None)
    ldap_username = ldap_username or settings.get("ldap_username", None)

    # set project parameters

    parameters = {}

    parameters["quotaclass"] = settings.get("quotaclass", "basic")
    parameters["quotamultiplier"] = settings.get("quotamultiplier", 1)
    parameters["quotamultiplier_compute"] = settings.get(
        "quotamultiplier_compute", None
    )
    parameters["quotamultiplier_network"] = settings.get(
        "quotamultiplier_network", None
    )
    parameters["quotamultiplier_storage"] = settings.get(
        "quotamultiplier_storage", None
    )
    parameters["quota_router"] = settings.get("quota_router", None)

    parameters["has_public_network"] = settings.get("has_public_network", True)
    parameters["has_service_network"] = settings.get("has_service_network", False)
    parameters["has_shared_images"] = settings.get("has_shared_images", False)

    params = [
        f"--cloud={cloud_name}",
        f"--domain={domain_name}",
        f"--quota-class={parameters['quotaclass']}",
        f"--quota-multiplier={parameters['quotamultiplier']}",
    ]

    if parameters["has_public_network"]:
        params.append("--has-public-network")
    else:
        params.append("--nohas-public-network")

    if parameters["has_service_network"]:
        params.append("--has-service-network")
    else:
        params.append("--nohas-service-network")

    if parameters["has_shared_images"]:
        params.append("--has-shared-images")
    else:
        params.append("--nohas-shared-images")

    if parameters["quotamultiplier_compute"]:
        params.append(
            f"--quota-multiplier-compute={parameters['quotamultiplier_compute']}"
        )
    if parameters["quotamultiplier_network"]:
        params.append(
            f"--quota-multiplier-network={parameters['quotamultiplier_network']}"
        )
    if parameters["quotamultiplier_storage"]:
        params.append(
            f"--quota-multiplier-storage={parameters['quotamultiplier_storage']}"
        )
    if parameters["quota_router"] is not None and parameters["quota_router"] >= 0:
        params.append(f"--quota-router={parameters['quota_router']}")

    # get ldap information

    conn = ldap.initialize(ldap_server)
    conn.simple_bind_s(ldap_username, ldap_password)

    search_filter = f"(&(objectClass={ldap_object_class})({ldap_group_cn}))"
    result = conn.search_s(
        ldap_base_dn, ldap.SCOPE_SUBTREE, search_filter, [ldap_search_attribute]
    )

    # check openstack projects

    os_cloud = openstack.connect(cloud=cloud_name)
    domain = os_cloud.identity.find_domain(domain_name)

    # cache roles
    CACHE_ROLES = {}
    for role in os_cloud.identity.roles():
        CACHE_ROLES[role.name] = role

    for a, b in result:

        if a != f"{ldap_group_cn},{ldap_base_dn}":
            continue

        for x in b[ldap_search_attribute]:
            username = x.decode("utf-8")

            logger.debug(f"Checking user {username}")
            user = os_cloud.identity.find_user(username, domain_id=domain.id)

            if not user:
                continue

            project = os_cloud.identity.find_project(
                f"{domain.name}-{username}", domain_id=domain.id
            )

            if project:
                continue

            # User does exist, but project does not exist

            command = f"tox -c {toxdir}/tox.ini -e create -- {' '.join(params)} --name={user.name}"
            result = subprocess.check_output(command, shell=True)

            # ensure that the user is assigned to the new project
            project = os_cloud.identity.find_project(
                f"{domain.name}-{username}", domain_id=domain.id
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
