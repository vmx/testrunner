import os
import time
from rabbit_helper import RabbitHelper
from cache import WorkloadCacher, TemplateCacher, BucketStatusCacher, cacheClean
import testcfg as cfg
import paramiko

# cleanup queues
rabbitHelper = RabbitHelper()

cached_queues = WorkloadCacher().queues +  TemplateCacher().cc_queues

test_queues = ["workload","workload_template"] + cached_queues

for queue in test_queues:
    try:
        if rabbitHelper.qsize(queue) > 0:
            print "Purge Queue: "+queue +" "+ str(rabbitHelper.qsize(queue))
            rabbitHelper.purge(queue)
    except Exception as ex:
        pass

cacheClean()

# kill old background processes
kill_procs=["sdkserver"]
for proc in kill_procs:
    os.system("ps aux | grep %s | awk '{print $2}' | xargs kill" % proc)

# start sdk servers
os.system("ruby sdkserver.rb &")
os.system("python sdkserver.py  &")
