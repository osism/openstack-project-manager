import unittest
from unittest.mock import MagicMock, patch

import string

import typer
from typer.testing import CliRunner

from openstack_project_manager.create_user import generate_password, run


app = typer.Typer()
app.command()(run)


class TestUtils(unittest.TestCase):

    def test_utils_0(self):
        password = generate_password(10)
        assert isinstance(password, str)
        assert len(password) == 10
        for char in password:
            assert char in (string.ascii_letters + string.digits)

        password2 = generate_password(10)
        assert isinstance(password2, str)
        assert len(password2) == 10
        for char in password2:
            assert char in (string.ascii_letters + string.digits)

        assert password != password2

        assert len(generate_password(100)) == 100
        assert len(generate_password(1)) == 1
        assert len(generate_password(0)) == 0
        assert len(generate_password(-1)) == 0


class TestCLI(unittest.TestCase):

    def setUp(self):
        self.patcher = patch("openstack.connect")
        self.mock_connect = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.mock_os_cloud = MagicMock()
        self.mock_connect.return_value = self.mock_os_cloud
        self.mock_os_domain = MagicMock()
        self.mock_os_domain.id = 1234
        self.mock_os_cloud.identity.find_domain.return_value = self.mock_os_domain
        self.mock_os_user = MagicMock()
        self.mock_os_user.id = 5678
        self.mock_os_cloud.identity.find_user.return_value = self.mock_os_user
        self.mock_os_project = MagicMock()
        self.mock_os_project.id = 9012
        self.mock_os_cloud.identity.find_project.return_value = self.mock_os_project

        self.os_roles = []
        for rolename in ["member", "load-balancer_member"]:
            role = MagicMock()
            role.name = rolename
            role.id = len(self.os_roles)
            self.os_roles.append(role)
        self.mock_os_cloud.identity.roles.return_value = self.os_roles

        self.patcher2 = patch("openstack_project_manager.create_user.generate_password")
        self.mock_generate_password = self.patcher2.start()
        self.addCleanup(self.patcher2.stop)
        self.mock_generate_password.return_value = "randompassword"

        self.runner = CliRunner()

    def test_cli_0(self):
        result = self.runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))
        self.mock_connect.assert_not_called()

    def test_cli_1(self):
        result = self.runner.invoke(app, ["--project-name=project"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_connect.assert_called_once_with(cloud="admin")
        self.mock_generate_password.assert_called_once_with(16)
        self.mock_os_cloud.identity.find_domain.assert_called_once_with("default")
        self.mock_os_cloud.identity.find_project.assert_called_once_with(
            "default-project", domain_id=self.mock_os_domain.id
        )
        self.mock_os_cloud.identity.find_user.assert_called_once_with(
            "", domain_id=self.mock_os_domain.id
        )
        self.mock_os_cloud.update_user.assert_called_once_with(
            self.mock_os_user, password="randompassword"
        )

        for role in self.os_roles:
            self.mock_os_cloud.identity.assign_project_role_to_user.assert_any_call(
                self.mock_os_project.id, self.mock_os_user.id, role.id
            )

    def test_cli_2(self):
        result = self.runner.invoke(
            app, ["--nodomain-name-prefix", "--project-name=project"]
        )
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.identity.find_project.assert_called_once_with(
            "project", domain_id=self.mock_os_domain.id
        )

    def test_cli_3(self):
        result = self.runner.invoke(app, ["--password-length=10"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_generate_password.assert_called_once_with(10)

    def test_cli_4(self):
        result = self.runner.invoke(app, ["--cloud=othercloud"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_connect.assert_called_once_with(cloud="othercloud")

    def test_cli_5(self):
        result = self.runner.invoke(
            app, ["--domain=otherdomain", "--project-name=project"]
        )
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.identity.find_domain.assert_called_once_with("otherdomain")
        self.mock_os_cloud.identity.find_project.assert_called_once_with(
            "otherdomain-project", domain_id=self.mock_os_domain.id
        )

    def test_cli_6(self):
        result = self.runner.invoke(app, ["--name=username"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.identity.find_user.assert_called_once_with(
            "username", domain_id=self.mock_os_domain.id
        )

    def test_cli_7(self):
        result = self.runner.invoke(app, ["--password=secret"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_generate_password.assert_not_called()
        self.mock_os_cloud.update_user.assert_called_once_with(
            self.mock_os_user, password="secret"
        )

    def test_cli_8(self):
        self.mock_os_cloud.identity.find_domain.return_value = None

        result = self.runner.invoke(
            app, ["--domain=notfound", "--project-name=project"]
        )
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.identity.find_domain.assert_called_once_with("notfound")
        self.mock_os_cloud.create_domain.assert_called_once_with(name="notfound")

    def test_cli_9(self):
        self.mock_os_cloud.identity.find_user.return_value = None

        result = self.runner.invoke(app, ["--name=notfound"])
        self.assertEqual(result.exit_code, 0, (result, result.stdout))

        self.mock_os_cloud.identity.find_user.assert_called_once_with(
            "notfound", domain_id=self.mock_os_domain.id
        )
        self.mock_os_cloud.create_user.assert_called_once_with(
            name="notfound",
            password="randompassword",
            default_project=self.mock_os_project,
            domain_id=self.mock_os_domain.id,
        )


if __name__ == "__main__":
    unittest.main()
