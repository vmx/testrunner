from basetestcase import BaseTestCase
from couchbase_helper.document import View
from couchbase_helper.documentgenerator import BlobGenerator
from membase.api.exception import RebalanceFailedException
from membase.api.rest_client import RestConnection


class RebalanceBaseTest(BaseTestCase):
    def setUp(self):
        super(RebalanceBaseTest, self).setUp()
        self.value_size = self.input.param("value_size", 256)
        self.doc_ops = self.input.param("doc_ops", None)
        self.withMutationOps = self.input.param("withMutationOps", True)
        self.total_vbuckets = self.input.param("total_vbuckets", 1024)
        if self.doc_ops is not None:
            self.doc_ops = self.doc_ops.split(":")
        self.defaul_map_func = "function (doc) {\n  emit(doc._id, doc);\n}"
        self.default_view_name = "default_view"
        self.default_view = View(self.default_view_name, self.defaul_map_func, None)
        self.std_vbucket_dist = self.input.param("std_vbucket_dist", None)
        self.zone = self.input.param("zone", 1)
        # define the data that will be used to test
        self.blob_generator = self.input.param("blob_generator", True)
        if self.blob_generator:
            # gen_load data is used for upload before each test(1000 items by default)
            self.gen_load = BlobGenerator('mike', 'mike-', self.value_size, end=self.num_items)
            # gen_update is used for doing mutation for 1/2th of uploaded data
            self.gen_update = BlobGenerator('mike', 'mike-', self.value_size, end=(self.num_items / 2 - 1))
            # upload data before each test
            self._load_all_buckets(self.servers[0], self.gen_load, "create", 0, flag=2, batch_size=20000)
        else:
            self._load_doc_data_all_buckets(batch_size=20000)

    def tearDown(self):
        super(RebalanceBaseTest, self).tearDown()
        """ Delete the new zones created if zone > 1. """
        if self.input.param("zone", 1) > 1:
            rest = RestConnection(self.servers[0])
            for i in range(1, int(self.input.param("zone", 1))):
                a = "Group "
                if rest.is_zone_exist(a + str(i + 1)):
                    rest.delete_zone(a + str(i + 1))

    def shuffle_nodes_between_zones_and_rebalance(self, to_remove=None):
        """
        Shuffle the nodes present in the cluster if zone > 1. Rebalance the nodes in the end.
        Nodes are divided into groups iteratively i.e. 1st node in Group 1, 2nd in Group 2, 3rd in Group 1 and so on, when
        zone=2.
        :param to_remove: List of nodes to be removed.
        """
        if not to_remove:
            to_remove = []
        serverinfo = self.servers[0]
        rest = RestConnection(serverinfo)
        zones = ["Group 1"]
        nodes_in_zone = {"Group 1": [serverinfo.ip]}
        # Create zones, if not existing, based on params zone in test.
        # Shuffle the nodes between zones.
        if int(self.zone) > 1:
            for i in range(1, int(self.zone)):
                a = "Group "
                zones.append(a + str(i + 1))
                if not rest.is_zone_exist(zones[i]):
                    rest.add_zone(zones[i])
                nodes_in_zone[zones[i]] = []
            # Divide the nodes between zones.
            nodes_in_cluster = [node.ip for node in self.get_nodes_in_cluster()]
            nodes_to_remove = [node.ip for node in to_remove]
            for i in range(1, len(self.servers)):
                if self.servers[i].ip in nodes_in_cluster and self.servers[i].ip not in nodes_to_remove:
                    server_group = i % int(self.zone)
                    nodes_in_zone[zones[server_group]].append(self.servers[i].ip)
            # Shuffle the nodesS
            for i in range(1, self.zone):
                node_in_zone = list(set(nodes_in_zone[zones[i]]) -
                                    set([node for node in rest.get_nodes_in_zone(zones[i])]))
                rest.shuffle_nodes_in_zones(node_in_zone, zones[0], zones[i])
        otpnodes = [node.id for node in rest.node_statuses()]
        nodes_to_remove = [node.id for node in rest.node_statuses() if node.ip in [t.ip for t in to_remove]]
        # Start rebalance and monitor it.
        started = rest.rebalance(otpNodes=otpnodes, ejectedNodes=nodes_to_remove)
        if started:
            result = rest.monitorRebalance()
            msg = "successfully rebalanced cluster {0}"
            self.log.info(msg.format(result))
        # Verify replicas of one node should not be in the same zone as active vbuckets of the node.
        if self.zone > 1:
            self._verify_replica_distribution_in_zones(nodes_in_zone)

    def add_remove_servers_and_rebalance(self, to_add, to_remove):
        """
        Add and/or remove servers and rebalance.
        :param to_add: List of nodes to be added.
        :param to_remove: List of nodes to be removed.
        """
        serverinfo = self.servers[0]
        rest = RestConnection(serverinfo)
        for node in to_add:
            rest.add_node(user=serverinfo.rest_username, password=serverinfo.rest_password,
                          remoteIp=node.ip)
        self.shuffle_nodes_between_zones_and_rebalance(to_remove)
