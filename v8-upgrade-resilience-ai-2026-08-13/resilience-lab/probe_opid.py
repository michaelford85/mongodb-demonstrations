import os

import pymongo
from pymongo import monitoring


class L(monitoring.CommandListener):
    def started(self, e):
        if e.command_name == "insert":
            print("STARTED op_id=%s req_id=%s conn=%s"
                  % (e.operation_id, e.request_id, e.connection_id))

    def succeeded(self, e):
        if e.command_name == "insert":
            print("SUCCEEDED op_id=%s req_id=%s" % (e.operation_id, e.request_id))

    def failed(self, e):
        if e.command_name == "insert":
            print("FAILED op_id=%s req_id=%s err=%s"
                  % (e.operation_id, e.request_id, e.failure.get("codeName")))


monitoring.register(L())
c = pymongo.MongoClient(os.environ["MONGODB_URI"], retryWrites=True)
c.admin.command({
    "configureFailPoint": "failCommand",
    "mode": {"times": 1},
    "data": {"failCommands": ["insert"], "errorCode": 10107,
             "errorLabels": ["RetryableWriteError"]},
})
print("inserted", c.probe.t.insert_one({"a": 1}).inserted_id)
c.admin.command({"configureFailPoint": "failCommand", "mode": "off"})
c.probe.drop_collection("t")
