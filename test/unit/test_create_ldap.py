import unittest
from unittest.mock import patch, MagicMock, ANY

import typer
from typer.testing import CliRunner
from typing import Any

from openstack_project_manager.create_ldap import run


app = typer.Typer()
app.command()(run)


def mock_settings(name: str, default: Any = None):
    d = {
        "ldap_base_dn": "settings_base_dn",
        "ldap_group_cn": "settings_group_cn",
        "ldap_object_class": "settings_object_class",
        "ldap_password": "settings_password",
        "ldap_search_attribute": "settings_search_attribute",
        "ldap_server": "settings_server",
        "ldap_username": "settings_username",
        "quotaclass": "settings_quota_class",
        "quotamultiplier": 2,
        "quotamultiplier_compute": 3,
        "quotamultiplier_network": 4,
        "quotamultiplier_storage": 5,
        "quota_router": 6,
        "has_public_network": False,
        "has_service_network": True,
        "has_shared_images": True,
    }

    return d[name] if name in d else default


class TestCLI(unittest.TestCase):

    def setUp(self):
        self.patcher = patch("openstack.connect")
        self.mock_connect = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.mock_os_cloud = MagicMock()
        self.mock_connect.return_value = self.mock_os_cloud
        self.mock_os_domain = MagicMock()
        self.mock_os_domain.id = 1234
        self.mock_os_domain.name = "domainname"
        self.mock_os_cloud.identity.find_domain.return_value = self.mock_os_domain
        self.mock_os_user = MagicMock()
        self.mock_os_user.id = 5678
        self.mock_os_cloud.identity.find_user.return_value = self.mock_os_user
        self.mock_os_project = MagicMock()
        self.mock_os_project.id = 9012
        self.mock_os_cloud.identity.find_project.return_value = self.mock_os_project
        self.mock_os_cloud.identity.find_project_called = False

        self.os_roles = []
        for rolename in ["member", "load-balancer_member"]:
            role = MagicMock()
            role.name = rolename
            role.id = len(self.os_roles)
            self.os_roles.append(role)
        self.mock_os_cloud.identity.roles.return_value = self.os_roles

        self.patcher2 = patch("ldap.initialize")
        self.mock_ldap_initialize = self.patcher2.start()
        self.addCleanup(self.patcher2.stop)
        self.mock_ldap_server = MagicMock()
        self.mock_ldap_server.search_s.return_value = [
            ("group,basedn", {"search": ["user".encode()]})
        ]
        self.mock_ldap_initialize.return_value = self.mock_ldap_server

        self.patcher3 = patch("subprocess.check_output")
        self.mock_check_output = self.patcher3.start()
        self.addCleanup(self.patcher3.stop)

        self.runner = CliRunner()

    def test_cli_0(self):
        result = self.runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))
        self.mock_connect.assert_not_called()

    def test_cli_1(self):
        result = self.runner.invoke(app, ["--debug"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

    def test_cli_2(self):
        result = self.runner.invoke(
            app,
            [
                "--ldap-server=test.example.ldap",
                "--ldap-username=ldapuser",
                "--ldap-password=ldappassword",
                "--ldap-base-dn=basedn",
                "--ldap-search-attribute=search",
                "--ldap-object-class=object_class",
                "--ldap-group-cn=group",
            ],
        )
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_ldap_initialize.assert_called_with("test.example.ldap")
        self.mock_ldap_server.simple_bind_s.assert_called_with(
            "ldapuser", "ldappassword"
        )
        self.mock_ldap_server.search_s.assert_called_with(
            "basedn", ANY, "(&(objectClass=object_class)(group))", ["search"]
        )

        self.mock_connect.assert_called_with(cloud="admin")
        self.mock_os_cloud.identity.find_domain.assert_called_with("default")
        self.mock_os_cloud.identity.find_user.assert_called_with("user", domain_id=1234)
        self.mock_os_cloud.identity.find_project.assert_called_with(
            "domainname-user", domain_id=1234
        )

        self.mock_ldap_server.unbind_s.assert_called_once()

    def test_cli_3(self):
        def mock_find_project(name: str, domain_id: int):
            if not self.mock_os_cloud.identity.find_project_called:
                self.mock_os_cloud.identity.find_project_called = True
                return None
            return self.mock_os_project

        self.mock_os_cloud.identity.find_project = mock_find_project

        result = self.runner.invoke(
            app,
            [
                "--ldap-server=test.example.ldap",
                "--ldap-username=ldapuser",
                "--ldap-password=ldappassword",
                "--ldap-base-dn=basedn",
                "--ldap-search-attribute=search",
                "--ldap-object-class=object_class",
                "--ldap-group-cn=group",
            ],
        )
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_check_output.assert_called_once()

        expected_parameters = [
            "--quota-class=basic",
            "--quota-multiplier=1",
            "--has-public-network",
            "--nohas-service-network",
            "--nohas-shared-images",
        ]

        args = self.mock_check_output.call_args.args[0]
        for param in expected_parameters:
            assert param in args, f"{param} not in '{args}'"

        for role in self.os_roles:
            self.mock_os_cloud.identity.assign_project_role_to_user.assert_any_call(
                self.mock_os_project.id, self.mock_os_user.id, role.id
            )

    def test_cli_4(self):
        result = self.runner.invoke(app, ["--cloud=othercloud"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_connect.assert_called_with(cloud="othercloud")

    def test_cli_5(self):
        result = self.runner.invoke(app, ["--domain=otherdomain"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.identity.find_domain.assert_called_with("otherdomain")

    @patch("openstack_project_manager.create_ldap.get_settings")
    def test_cli_6(self, mock_get_settings):
        mock_dynaconf = MagicMock()
        mock_get_settings.return_value = mock_dynaconf
        mock_dynaconf.get = mock_settings
        self.mock_ldap_server.search_s.return_value = [
            (
                "settings_group_cn,settings_base_dn",
                {"settings_search_attribute": ["user".encode()]},
            )
        ]

        result = self.runner.invoke(app, [])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_ldap_initialize.assert_called_with("settings_server")
        self.mock_ldap_server.simple_bind_s.assert_called_with(
            "settings_username", "settings_password"
        )
        self.mock_ldap_server.search_s.assert_called_with(
            "settings_base_dn",
            ANY,
            "(&(objectClass=settings_object_class)(settings_group_cn))",
            ["settings_search_attribute"],
        )

        self.mock_connect.assert_called_with(cloud="admin")
        self.mock_os_cloud.identity.find_domain.assert_called_with("default")
        self.mock_os_cloud.identity.find_user.assert_called_with("user", domain_id=1234)
        self.mock_os_cloud.identity.find_project.assert_called_with(
            "domainname-user", domain_id=1234
        )

        self.mock_ldap_server.unbind_s.assert_called_once()

    @patch("openstack_project_manager.create_ldap.get_settings")
    def test_cli_7(self, mock_get_settings):
        def mock_find_project(name: str, domain_id: int):
            if not self.mock_os_cloud.identity.find_project_called:
                self.mock_os_cloud.identity.find_project_called = True
                return None
            return self.mock_os_project

        self.mock_os_cloud.identity.find_project = mock_find_project

        mock_dynaconf = MagicMock()
        mock_get_settings.return_value = mock_dynaconf
        mock_dynaconf.get = mock_settings
        self.mock_ldap_server.search_s.return_value = [
            (
                "settings_group_cn,settings_base_dn",
                {"settings_search_attribute": ["user".encode()]},
            )
        ]

        result = self.runner.invoke(app, [])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_check_output.assert_called_once()

        expected_parameters = [
            "--quota-class=settings_quota_class",
            "--quota-multiplier=2",
            "--quota-multiplier-compute=3",
            "--quota-multiplier-network=4",
            "--quota-multiplier-storage=5",
            "--quota-router=6",
            "--nohas-public-network",
            "--has-service-network",
            "--has-shared-images",
        ]

        args = self.mock_check_output.call_args.args[0]
        for param in expected_parameters:
            assert param in args, f"{param} not in '{args}'"

        for role in self.os_roles:
            self.mock_os_cloud.identity.assign_project_role_to_user.assert_any_call(
                self.mock_os_project.id, self.mock_os_user.id, role.id
            )


if __name__ == "__main__":
    unittest.main()
