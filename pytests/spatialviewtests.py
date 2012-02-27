import random
from threading import Thread
import unittest
import uuid
import logger
import time

from membase.helper.spatial_helper import SpatialHelper
from membase.helper.failover_helper import FailoverHelper

from TestInput import TestInputSingleton

class SpatialViewTests(unittest.TestCase):
    def setUp(self):
        TestInputSingleton.input.test_params["skip_cleanup"] = True
        self.log = logger.Logger.get_logger()
        self.helper = SpatialHelper(self, "default")
        self.helper.setup_cluster()


    def tearDown(self):
        self.helper.cleanup_cluster()


    def test_create_multiple_development_spatial(self):
        self.log.info("description : create multiple spatial views without "
                      "running any spatial view query")
        rest = self.helper.rest
        bucket = self.helper.bucket
        prefix = str(uuid.uuid4())
        name = "dev_test_spatial_multiple"

        design_names = ["{0}-{1}-{2}".format(name, i, prefix) \
                             for i in range(0, 5)]
        for design_name in design_names:
            self.helper.create_index_fun(design_name, prefix)
            response = rest.get_spatial(bucket, design_name)
            self.assertTrue(response)
            self.assertEquals(response["_id"],
                              "_design/{0}".format(design_name))
            self.log.info(response)


    def test_insert_x_docs(self):
        num_docs = self.helper.input.param("num-docs", 100)
        self.log.info("description : create a spatial view on {0} documents"\
                          .format(num_docs))
        design_name = "dev_test_insert_{0}_docs".format(num_docs)
        self._insert_x_docs_and_query(num_docs, design_name)


    # Does verify the full docs and not only the keys
    def test_insert_x_docs_full_verification(self):
        num_docs = self.helper.input.param("num-docs", 100)
        self.log.info("description : create a spatial view with {0} docs"
                      " and verify the full documents".format(num_docs))
        design_name = "dev_test_insert_{0}_docs_full_verification"\
            .format(num_docs)
        prefix = str(uuid.uuid4())[:7]

        self.helper.create_index_fun(design_name, prefix)
        inserted_docs = self.helper.insert_docs(num_docs, prefix,
                                                return_docs=True)
        self.helper.query_index_for_verification(design_name, inserted_docs,
                                                 full_docs=True)


    def test_insert_x_delete_y_docs(self):
        num_docs = self.helper.input.param("num-docs", 15000)
        num_deleted_docs = self.helper.input.param("num-deleted-docs", 10000)
        self.log.info("description : create spatial view with {0} docs "
                      " and delete {1} docs".format(num_docs,
                                                    num_deleted_docs))
        design_name = "dev_test_insert_{0}_delete_{1}_docs"\
            .format(num_docs, num_deleted_docs)
        prefix = str(uuid.uuid4())[:7]

        inserted_keys = self._setup_index(design_name, num_docs, prefix)

        # Delete documents and very that the documents got deleted
        deleted_keys = self.helper.delete_docs(num_deleted_docs, prefix)
        results = self.helper.get_results(design_name, 2*num_docs)
        result_keys = self.helper.get_keys(results)
        self.assertEqual(len(result_keys), num_docs-len(deleted_keys))
        self.helper.verify_result(inserted_keys, deleted_keys + result_keys)


    def test_insert_x_update_y_docs(self):
        num_docs = self.helper.input.param("num-docs", 15000)
        num_updated_docs = self.helper.input.param("num-updated-docs", 100)
        self.log.info("description : create spatial view with {0} docs "
                      " and update {1} docs".format(num_docs,
                                                    num_updated_docs))
        design_name = "dev_test_insert_{0}_delete_{1}_docs"\
            .format(num_docs, num_updated_docs)
        prefix = str(uuid.uuid4())[:7]

        self._setup_index(design_name, num_docs, prefix)

        # Update documents and verify that the documents got updated
        updated_keys = self.helper.insert_docs(num_updated_docs, prefix,
                                               dict(updated=True))
        results = self.helper.get_results(design_name, 2*num_docs)
        result_updated_keys = self._get_updated_docs_keys(results)
        self.assertEqual(len(updated_keys), len(result_updated_keys))
        self.helper.verify_result(updated_keys, result_updated_keys)


    def test_get_spatial_during_x_min_load_y_working_set(self):
        num_docs = self.helper.input.param("num-docs", 10000)
        duration = self.helper.input.param("load-time", 1)
        self.log.info("description : this test will continuously insert data "
                      "and get the spatial view results for {0} minutes")
        design_name = "dev_test_insert_and_get_spatial_{0}_mins"\
            .format(duration)
        prefix = str(uuid.uuid4())[:7]

        self.helper.create_index_fun(design_name, prefix)

        self.docs_inserted = []
        self.shutdown_load_data = False
        load_thread = Thread(
            target=self._insert_data_till_stopped,
            args=(num_docs, prefix))
        load_thread.start()

        self._get_results_for_x_minutes(design_name, duration)

        self.shutdown_load_data = True
        load_thread.join()

        # self.docs_inserted was set by the insertion thread
        # (_insert_data_till_stopped)
        self.helper.query_index_for_verification(design_name,
                                                 self.docs_inserted)


    def test_spatial_view_on_x_docs_y_design_docs(self):
        num_docs = self.helper.input.param("num-docs", 10000)
        num_design_docs = self.helper.input.param("num-design-docs", 21)
        self.log.info("description : will create {0} docs per design doc and "
                      "{1} design docs that will be queried")
        name = "dev_test_spatial_test_{0}_docs_y_design_docs"\
            .format(num_docs, num_design_docs)
        #prefix = str(uuid.uuid4())[:7]
        prefix = "fixed"

        design_names = ["{0}-{1}-{2}".format(name, i, prefix) \
                            for i in range(0, num_design_docs)]

        view_test_threads = []
        for design_name in design_names:
            thread_result = []
            t = Thread(
                target=SpatialViewTests._test_spatial_view_thread_wrapper,
                name="Insert documents and query in parallel",
                args=(self, num_docs, design_name, thread_result))
            t.start()
            view_test_threads.append((t, thread_result))
        for (t, failures) in view_test_threads:
            t.join()
        for (t, failures) in view_test_threads:
            if len(failures) > 0:
                self.fail("view thread failed : {0}".format(failures[0]))


    def _test_spatial_view_thread_wrapper(self, num_docs, design_name,
                                          failures):
        try:
            self._insert_x_docs_and_query(num_docs, design_name)
        except Exception as ex:
            failures.append(ex)


    # Create the index and insert documents including verififaction that
    # the index contains them
    # Returns the keys of the inserted documents
    def _setup_index(self, design_name, num_docs, prefix):
        self.helper.create_index_fun(design_name, prefix)
        inserted_keys = self.helper.insert_docs(num_docs, prefix)
        self.helper.query_index_for_verification(design_name, inserted_keys)

        return inserted_keys


    # Return the keys for all docs that contain a key called "updated"
    # in the value
    def _get_updated_docs_keys(self, results):
        keys = []
        if results:
            rows = results["rows"]
            for row in rows:
                if "updated" in row["value"]:
                    keys.append(row["id"].encode("ascii", "ignore"))
            self.log.info("{0} documents to updated".format(len(keys)))
        return keys


    def _get_results_for_x_minutes(self, design_name, duration, delay=5):
        random.seed(0)
        start = time.time()
        while (time.time() - start) < duration * 60:
            limit = random.randint(1, 1000)
            self.log.info("{0} seconds has passed ....".format(
                    (time.time() - start)))
            results = self.helper.get_results(design_name, limit)
            keys = self.helper.get_keys(results)
            self.log.info("spatial view returned {0} rows".format(len(keys)))
            time.sleep(delay)

    def _insert_data_till_stopped(self, num_docs, prefix):
        while not self.shutdown_load_data:
            # Will be read after the function is terminated
            self.docs_inserted = self.helper.insert_docs(
                num_docs, prefix, wait_for_persistence=False)

    def _insert_x_docs_and_query(self, num_docs, design_name):
        prefix = str(uuid.uuid4())[:7]

        inserted_keys = self._setup_index(design_name, num_docs, prefix)
        self.assertEqual(len(inserted_keys), num_docs)

    def test_x_docs_failover(self):
        num_docs = self.helper.input.param("num-docs", 10000)
        self.log.info("description : test failover with {0} documents"\
                          .format(num_docs))
        design_name = "dev_test_failover_{0}".format(num_docs)
        prefix = str(uuid.uuid4())[:7]

        fh = FailoverHelper(self.helper.servers, self)

        inserted_keys = self._setup_index(design_name, num_docs, prefix)
        failover_nodes = fh.failover(1)
        self.helper.query_index_for_verification(design_name, inserted_keys)

        # The test cleanup expects all nodes running, hence spin the
        # full cluster up again
        fh.undo_failover(failover_nodes)
