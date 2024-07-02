import unittest
from unittest.mock import MagicMock, patch, ANY, call

import copy
import string
import yaml

import typer
from typer.testing import CliRunner

from openstack_project_manager.manage import (
    Configuration,
    get_quotaclass,
    check_bool,
    check_quota,
    manage_external_network_rbacs,
    check_volume_types,
    create_network_resources,
    add_service_network,
    del_service_network,
    add_external_network,
    del_external_network,
    create_service_network,
    create_network,
    create_network_with_router,
    check_homeproject_permissions,
    run,
)


app = typer.Typer()
app.command()(run)

MOCK_QUOTA_CLASSES = yaml.safe_load(
    """
---
default:
  compute:
    cores: 1
    injected_file_content_bytes: 10240
    instances: 255
  network:
    floatingip: 1
    network: 1
    router: 1
  volume:
    backup_gigabytes: 1
    backups: 1
    gigabytes: 1


unlimited:
  parent: default
  compute:
    cores: -1


volume_test:
  parent: default
  volume_types:
    item1:
      name: name
"""
)


class CloudTest(unittest.TestCase):

    def setUp(self):
        self.patcher = patch("openstack.connect")
        self.mock_connect = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.mock_os_cloud = MagicMock()
        self.mock_connect.return_value = self.mock_os_cloud

        self.mock_os_keystone = MagicMock()
        self.mock_os_neutron = MagicMock()

        def mock_make_client(name: str, cloud: str):
            if name == "identity":
                return self.mock_os_keystone
            elif name == "network":
                return self.mock_os_neutron

        self.patcher2 = patch("os_client_config.make_client")
        self.mock_make_client = self.patcher2.start()
        self.mock_make_client.side_effect = mock_make_client
        self.addCleanup(self.patcher2.stop)

        self.os_roles = []
        for rolename in ["member", "load-balancer_member"]:
            role = MagicMock()
            role.name = rolename
            role.id = len(self.os_roles)
            self.os_roles.append(role)
        self.mock_os_cloud.identity.roles.return_value = self.os_roles


class TestConfiguration(CloudTest):

    def setUp(self):
        super().setUp()
        self.patcher3 = patch("builtins.open")
        self.mock_open = self.patcher3.start()
        self.addCleanup(self.patcher3.stop)

        self.patcher4 = patch("yaml.load")
        self.mock_yaml_load = self.patcher4.start()
        self.addCleanup(self.patcher4.stop)
        self.mock_yaml_load.return_value = ["a", "b", "c"]

    def test_configuration_0(self):
        config = Configuration(
            False, "cloud-name", "endpoints.yml", True, "admin-domain"
        )

        assert not config.dry_run
        assert config.ENDPOINTS == ["a", "b", "c"]
        self.mock_connect.assert_called_once_with(cloud="cloud-name")
        assert config.os_cloud is self.mock_os_cloud
        assert config.os_keystone is self.mock_os_keystone
        assert config.os_neutron is self.mock_os_neutron
        assert len(config.CACHE_ROLES) > 0
        assert config.assign_admin_user
        self.mock_os_cloud.identity.find_domain.assert_called_once_with("admin-domain")

    def test_configuration_1(self):
        config = Configuration(
            True, "cloud-name", "endpoints.yml", False, "admin-domain"
        )

        assert config.dry_run
        assert not config.assign_admin_user


class TestUtils(unittest.TestCase):

    def setUp(self):
        self.patcher = patch("builtins.open")
        self.mock_open = self.patcher.start()
        self.addCleanup(self.patcher.stop)

        self.patcher2 = patch("yaml.load")
        self.mock_yaml_load = self.patcher2.start()
        self.addCleanup(self.patcher2.stop)
        self.mock_yaml_load.return_value = MOCK_QUOTA_CLASSES

    def test_get_quotaclass_0(self):
        result = get_quotaclass("classes.yaml", "default")
        self.mock_open.assert_called_once_with("classes.yaml", "r")
        self.mock_yaml_load.assert_called_once()
        assert result == MOCK_QUOTA_CLASSES["default"]

    def test_get_quotaclass_1(self):
        result = get_quotaclass("classes.yaml", "notfound")
        assert result is None

    def test_get_quotaclass_2(self):
        result = get_quotaclass("classes.yaml", "unlimited")
        assert result["compute"]["cores"] == -1
        result["compute"]["cores"] = MOCK_QUOTA_CLASSES["default"]["compute"]["cores"]
        assert result == MOCK_QUOTA_CLASSES["default"]

    def test_check_bool_0(self):
        project = MagicMock()
        project.__contains__.return_value = True
        project.get.return_value = "true"
        assert check_bool(project, "param") == True
        project.get.return_value = "True"
        assert check_bool(project, "param") == True
        project.get.return_value = "yes"
        assert check_bool(project, "param") == True
        project.get.return_value = "Yes"
        assert check_bool(project, "param") == True
        project.get.return_value = "false"
        assert check_bool(project, "param") == False
        project.get.return_value = "False"
        assert check_bool(project, "param") == False
        project.get.return_value = "no"
        assert check_bool(project, "param") == False
        project.get.return_value = "No"
        assert check_bool(project, "param") == False
        project.get.return_value = "Nothing"
        assert check_bool(project, "param") == False


class TestBase(CloudTest):

    def setUp(self):
        super().setUp()

        self.patcher3 = patch("builtins.open")
        self.mock_open = self.patcher3.start()
        self.addCleanup(self.patcher3.stop)

        self.patcher4 = patch("yaml.load")
        self.mock_yaml_load = self.patcher4.start()
        self.addCleanup(self.patcher4.stop)
        self.mock_yaml_load.return_value = ["a", "b", "c"]

        self.config = Configuration(
            False, "cloud-name", "endpoints.yml", True, "admin-domain"
        )
        for rolename in ["member", "load-balancer_member"]:
            self.config.CACHE_ROLES[rolename] = MagicMock()
            self.config.CACHE_ROLES[rolename].id = len(self.config.CACHE_ROLES)

        if not hasattr(self, "select_quota_class"):
            self.select_quota_class = "default"

        self.patcher5 = patch("openstack_project_manager.manage.get_quotaclass")
        self.mock_get_quotaclass = self.patcher5.start()
        self.mock_get_quotaclass.return_value = copy.copy(
            MOCK_QUOTA_CLASSES[self.select_quota_class]
        )
        self.addCleanup(self.patcher5.stop)


class TestCheckQuota(TestBase):

    def test_check_quota_0(self):
        # Network Quotas
        mock_project = MagicMock()
        mock_project.name = "service"
        mock_project.quotamultiplier_network = "5"
        mock_project.quota_router = "6"
        mock_project.__contains__.return_value = True

        self.mock_os_cloud.get_network_quotas.return_value = {
            "floatingip": 5,
            "network": 0,
            "router": 0,
        }

        check_quota(self.config, mock_project, "classes.yaml")

        assert self.mock_os_cloud.set_network_quotas.call_count == 2
        self.mock_os_cloud.set_network_quotas.assert_any_call(ANY, network=5)
        self.mock_os_cloud.set_network_quotas.assert_any_call(ANY, router=6)

    def test_check_quota_1(self):
        # Compute Quotas
        mock_project = MagicMock()
        mock_project.name = "admin"
        mock_project.quotamultiplier_compute = "4"
        mock_project.__contains__.return_value = True

        self.mock_os_cloud.get_compute_quotas.return_value = {
            "cores": 0,
            "injected_file_content_bytes": 0,
            "instances": 4,
        }

        check_quota(self.config, mock_project, "classes.yaml")

        assert self.mock_os_cloud.set_compute_quotas.call_count == 3
        self.mock_os_cloud.set_compute_quotas.assert_any_call(ANY, cores=4)
        self.mock_os_cloud.set_compute_quotas.assert_any_call(
            ANY, injected_file_content_bytes=10240
        )
        self.mock_os_cloud.set_compute_quotas.assert_any_call(ANY, instances=1020)

    def test_check_quota_2(self):
        # Volume Quotas
        mock_project = MagicMock()
        mock_project.name = "other"
        mock_project.quotamultiplier_storage = "3"
        mock_project.__contains__.return_value = True
        mock_project.quotaclass = "other"

        self.mock_os_cloud.get_volume_quotas.return_value = {
            "backup_gigabytes": 0,
            "backups": 0,
            "gigabytes": 0,
        }

        check_quota(self.config, mock_project, "classes.yaml")

        assert self.mock_os_cloud.set_volume_quotas.call_count == 3
        self.mock_os_cloud.set_volume_quotas.assert_any_call(ANY, backup_gigabytes=3)
        self.mock_os_cloud.set_volume_quotas.assert_any_call(ANY, backups=3)
        self.mock_os_cloud.set_volume_quotas.assert_any_call(ANY, gigabytes=3)


class TestManageExternalNetworkRbacs(TestBase):

    def setUp(self):
        super().setUp()

        self.mock_domain = MagicMock()
        self.mock_domain.name = "not_default"

    @patch("openstack_project_manager.manage.add_service_network")
    @patch("openstack_project_manager.manage.add_external_network")
    def test_manage_external_network_rbacs_0(
        self, mock_add_external_network, mock_add_service_network
    ):
        mock_project = MagicMock()
        mock_project.__contains__.return_value = True
        mock_project.get.return_value = "True"
        mock_project.public_network = "public_network_name"
        mock_project.service_network = "servic_network_name"

        manage_external_network_rbacs(
            self.config, mock_project, self.mock_domain, "classes.yaml"
        )

        mock_add_external_network.assert_called_once_with(
            self.config, mock_project, "public_network_name"
        )
        mock_add_service_network.assert_called_once_with(
            self.config, mock_project, "servic_network_name"
        )

    @patch("openstack_project_manager.manage.del_service_network")
    @patch("openstack_project_manager.manage.del_external_network")
    def test_manage_external_network_rbacs_1(
        self, mock_del_external_network, mock_del_service_network
    ):
        mock_project = MagicMock()
        mock_project.__contains__.return_value = False
        mock_project.get.return_value = "False"

        manage_external_network_rbacs(
            self.config, mock_project, self.mock_domain, "classes.yaml"
        )

        mock_del_external_network.assert_called_once_with(
            self.config, mock_project, "public"
        )
        mock_del_service_network.assert_called_once_with(
            self.config, mock_project, "not_default-service"
        )


class TestCheckVolumeTypes(TestBase):

    def setUp(self):
        self.select_quota_class = "volume_test"
        super().setUp()

        self.mock_project = MagicMock()
        self.mock_project.id = 1234

    def test_check_volume_types_0(self):
        self.mock_project.__contains__.return_value = True

        self.config.os_cloud.block_storage.types.return_value = ["volume_type"]

        check_volume_types(self.config, self.mock_project, MagicMock(), "classes.yaml")

        self.config.os_cloud.block_storage.types.assert_called_once_with(
            name="item1", is_public="False"
        )
        self.config.os_cloud.block_storage.add_type_access.assert_called_with(
            "volume_type", 1234
        )

    def test_check_volume_types_1(self):
        self.mock_project.__contains__.return_value = False

        self.config.os_cloud.block_storage.types.return_value = [
            "volume_type",
            "volume_type_2",
        ]
        check_volume_types(self.config, self.mock_project, MagicMock(), "classes.yaml")
        self.config.os_cloud.block_storage.add_type_access.assert_not_called()

        self.config.os_cloud.block_storage.types.return_value = []
        check_volume_types(self.config, self.mock_project, MagicMock(), "classes.yaml")
        self.config.os_cloud.block_storage.add_type_access.assert_not_called()


class TestCreateNetworkResources(TestBase):

    @patch("openstack_project_manager.manage.create_network_with_router")
    def test_create_network_resources_0(self, mock_create_network_with_router):
        mock_project = MagicMock()
        mock_project.name = "project_name"
        mock_project.__contains__.return_value = True
        mock_project.quotamultiplier = "1"
        mock_project.quotamultiplier_network = "2"

        def mock_get(name: str):
            return name != "is_service_project"

        mock_project.get.side_effect = mock_get
        mock_project.public_network = "public_network_name"
        mock_project.service_network = "service_network_name"

        mock_domain = MagicMock()
        mock_domain.name = "not_default"

        create_network_resources(self.config, mock_project, mock_domain)

        mock_create_network_with_router.assert_any_call(
            self.config,
            mock_project,
            "net-to-public_network_name-project_name",
            "subnet-to-public_network_name-project_name",
            "router-to-public_network_name-project_name",
            "public_network_name",
            "nova",
        )

        mock_create_network_with_router.assert_any_call(
            self.config,
            mock_project,
            "net-to-service_network_name-project_name",
            "subnet-to-service_network_name-project_name",
            "router-to-service_network_name-project_name",
            "service_network_name",
            "nova",
        )

    @patch("openstack_project_manager.manage.create_service_network")
    @patch("openstack_project_manager.manage.create_network_with_router")
    def test_create_network_resources_1(
        self, mock_create_network_with_router, mock_create_service_network
    ):
        mock_project = MagicMock()
        mock_project.name = "project_name"

        def mock_get(name: str):
            return (
                name == "has_service_network"
                or name == "has_public_network"
                or name == "is_service_project"
            )

        mock_project.__contains__.side_effect = mock_get
        mock_project.get.side_effect = mock_get
        mock_project.service_network_cidr = "cdir"

        mock_domain = MagicMock()
        mock_domain.name = "not_default"

        create_network_resources(self.config, mock_project, mock_domain)

        mock_create_network_with_router.assert_not_called()
        mock_create_service_network.assert_called_once_with(
            self.config,
            mock_project,
            "not_default-service",
            "subnet-not_default-service",
            "nova",
            "cdir",
        )


class TestModifyNetwork(TestBase):

    def setUp(self):
        super().setUp()

        self.mock_project = MagicMock()
        self.mock_project.id = 1234

        self.mock_network = MagicMock()
        self.mock_network.id = 5678
        self.config.os_cloud.get_network.return_value = self.mock_network

    def test_add_service_network(self):
        self.mock_project.__contains__.return_value = True
        self.mock_project.service_network_type = "network_type_name"

        add_service_network(self.config, self.mock_project, "network_name")

        self.config.os_cloud.get_network.assert_called_once_with("network_name")
        self.config.os_neutron.list_rbac_policies.assert_called_once_with(
            target_tenant=1234,
            action="access_as_network_type_name",
            object_type="network",
            object_id=5678,
            fields="id",
        )
        self.config.os_neutron.create_rbac_policy.assert_called_once_with(
            {
                "rbac_policy": {
                    "target_tenant": 1234,
                    "action": "access_as_network_type_name",
                    "object_type": "network",
                    "object_id": 5678,
                }
            }
        )

    def test_del_service_network(self):
        del_service_network(self.config, self.mock_project, "network_name")

        self.config.os_cloud.get_network.assert_called_once_with("network_name")
        self.config.os_neutron.list_rbac_policies.assert_called_once_with(
            target_tenant=1234,
            action="access_as_shared",
            object_type="network",
            object_id=5678,
            fields="id",
        )
        self.config.os_neutron.delete_rbac_policy.assert_not_called()

        self.config.os_neutron.list_rbac_policies.return_value = {
            "rbac_policies": [{"id": 9012}]
        }
        del_service_network(self.config, self.mock_project, "network_name")
        self.config.os_neutron.delete_rbac_policy.assert_called_once_with(9012)

    def test_add_external_network(self):
        add_external_network(self.config, self.mock_project, "network_name")

        self.config.os_cloud.get_network.assert_called_once_with("network_name")
        self.config.os_neutron.list_rbac_policies.assert_called_once_with(
            target_tenant=1234,
            action="access_as_external",
            object_type="network",
            object_id=5678,
            fields="id",
        )
        self.config.os_neutron.create_rbac_policy.assert_called_once_with(
            {
                "rbac_policy": {
                    "target_tenant": 1234,
                    "action": "access_as_external",
                    "object_type": "network",
                    "object_id": 5678,
                }
            }
        )

    def test_del_external_network(self):
        del_external_network(self.config, self.mock_project, "network_name")

        self.config.os_cloud.get_network.assert_called_once_with("network_name")
        self.config.os_neutron.list_rbac_policies.assert_called_once_with(
            target_tenant=1234,
            action="access_as_external",
            object_type="network",
            object_id=5678,
            fields="id",
        )
        self.config.os_neutron.delete_rbac_policy.assert_not_called()

        self.config.os_neutron.list_rbac_policies.return_value = {
            "rbac_policies": [{"id": 9012}]
        }
        del_external_network(self.config, self.mock_project, "network_name")
        self.config.os_neutron.delete_rbac_policy.assert_called_once_with(9012)


class TestCreateNetwork(TestBase):

    def setUp(self):
        super().setUp()
        self.mock_project = MagicMock()
        self.mock_project.id = 9999
        self.mock_project.domain_id = 1234
        self.mock_project.name = "project_name"

        mock_domain = MagicMock()
        mock_domain.name = "domain_name"
        self.config.os_cloud.get_domain.return_value = mock_domain

        self.mock_service_project = MagicMock()
        self.mock_service_project.id = 5678
        self.config.os_cloud.get_project.return_value = self.mock_service_project

        self.mock_network = MagicMock()
        self.mock_network.id = 9012
        self.config.os_cloud.create_network.return_value = self.mock_network

        self.mock_subnet = MagicMock()
        self.mock_subnet.id = 1111
        self.config.os_cloud.create_subnet.return_value = self.mock_subnet

    @patch("openstack_project_manager.manage.add_service_network")
    def test_create_service_network_0(self, mock_add_service_network):
        self.config.os_cloud.get_network.return_value = None
        self.config.os_cloud.get_subnet.return_value = None

        create_service_network(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
            "subnet_cidr",
        )

        self.config.os_cloud.create_network.assert_called_once_with(
            "network_name",
            project_id=5678,
            availability_zone_hints=["availability_zone"],
        )
        mock_add_service_network.assert_called_once_with(
            self.config, self.mock_service_project, "network_name"
        )
        self.config.os_cloud.create_subnet.assert_called_once_with(
            9012,
            tenant_id=5678,
            subnet_name="subnet_name",
            cidr="subnet_cidr",
            enable_dhcp=True,
        )

    @patch("openstack_project_manager.manage.add_service_network")
    def test_create_service_network_1(self, mock_add_service_network):
        self.config.os_cloud.get_network.return_value = self.mock_network
        self.config.os_cloud.get_subnet.return_value = None

        create_service_network(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
            None,
        )

        self.config.os_cloud.create_network.assert_not_called()
        mock_add_service_network.assert_not_called()
        self.config.os_cloud.create_subnet.assert_called_once_with(
            9012,
            tenant_id=5678,
            subnet_name="subnet_name",
            use_default_subnetpool=True,
            enable_dhcp=True,
        )

    @patch("openstack_project_manager.manage.add_service_network")
    def test_create_service_network_2(self, mock_add_service_network):
        self.config.os_cloud.get_subnet.return_value = self.mock_subnet

        create_service_network(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
            None,
        )

        self.config.os_cloud.create_subnet.assert_not_called()

    def test_create_network_0(self):
        self.config.os_cloud.get_network.return_value = None
        self.config.os_cloud.get_subnet.return_value = None

        attach, subnet = create_network(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
        )

        assert attach == True
        assert subnet is self.mock_subnet

        self.config.os_cloud.create_network.assert_called_once_with(
            "network_name",
            project_id=9999,
            availability_zone_hints=["availability_zone"],
        )
        self.config.os_cloud.create_subnet.assert_called_once_with(
            9012,
            tenant_id=9999,
            subnet_name="subnet_name",
            use_default_subnetpool=True,
            enable_dhcp=True,
        )

    def test_create_network_1(self):
        self.config.os_cloud.get_network.return_value = self.mock_network
        self.config.os_cloud.get_subnet.return_value = self.mock_subnet

        attach, subnet = create_network(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
        )

        assert attach == False
        assert subnet is self.mock_subnet

        self.config.os_cloud.create_network.assert_not_called()
        self.config.os_cloud.create_subnet.assert_not_called()

    @patch("openstack_project_manager.manage.create_network")
    def test_create_network_with_router_0(self, mock_create_network):
        mock_router = MagicMock()
        self.config.os_cloud.create_router.return_value = mock_router
        self.config.os_cloud.get_router.return_value = None
        self.config.os_cloud.get_network.return_value = self.mock_network
        mock_create_network.return_value = (False, self.mock_subnet)

        create_network_with_router(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "router_name",
            "public_net_name",
            "availability_zone",
        )

        self.config.os_cloud.create_router.assert_called_once_with(
            name="router_name",
            ext_gateway_net_id=9012,
            enable_snat=True,
            project_id=9999,
            availability_zone_hints=["availability_zone"],
        )

        mock_create_network.assert_called_once_with(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
        )

        self.config.os_cloud.add_router_interface.assert_called_once_with(
            mock_router, subnet_id=1111
        )

    @patch("openstack_project_manager.manage.create_network")
    def test_create_network_with_router_1(self, mock_create_network):
        mock_router = MagicMock()
        self.config.os_cloud.get_router.return_value = mock_router
        mock_create_network.return_value = (True, self.mock_subnet)

        create_network_with_router(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "router_name",
            "public_net_name",
            "availability_zone",
        )

        self.config.os_cloud.create_router.assert_not_called()

        mock_create_network.assert_called_once_with(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
        )

        self.config.os_cloud.add_router_interface.assert_called_once_with(
            mock_router, subnet_id=1111
        )

    @patch("openstack_project_manager.manage.create_network")
    def test_create_network_with_router_2(self, mock_create_network):
        mock_router = MagicMock()
        self.config.os_cloud.get_router.return_value = mock_router
        mock_create_network.return_value = (False, self.mock_subnet)

        create_network_with_router(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "router_name",
            "public_net_name",
            "availability_zone",
        )

        self.config.os_cloud.create_router.assert_not_called()

        mock_create_network.assert_called_once_with(
            self.config,
            self.mock_project,
            "network_name",
            "subnet_name",
            "availability_zone",
        )

        self.config.os_cloud.add_router_interface.assert_not_called()


class TestCheckHomeprojectPermissions(TestBase):

    def setUp(self):
        super().setUp()


#        self.mock_project = MagicMock()
#        self.mock_project.id = 1234
#        self.mock_project.__contains__.return_value = True
#        self.mock_project.get.return_value = "True"
#        self.mock_project.name = "default-username"

#        self.mock_domain = MagicMock()
#        self.mock_domain.id = 5678
#        self.mock_domain.__len__.return_value = 7

#        self.mock_user = MagicMock()
#        self.mock_user.id = 9012
#        def mock_find_user(name, domain_id):
#            if name == "username":
#                return self.mock_user
#            return None

#        self.config.os_cloud.identity.find_user.side_effect = mock_find_user

#    def test_check_homeproject_permissions_0(self):
#        check_homeproject_permissions(self.config, self.mock_project, self.mock_domain)

#        assert self.config.os_cloud.identity.assign_project_role_to_user.mock_calls, self.config.os_cloud.identity.assign_project_role_to_user.mock_calls
#        for rolename in self.config.CACHE_ROLES:
#            self.config.os_cloud.identity.assign_project_role_to_user.assert_any_call(
#                1234,
#                9012,
#                self.config.CACHE_ROLES[rolename].id
#            )

if __name__ == "__main__":
    unittest.main()
