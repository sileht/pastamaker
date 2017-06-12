# -*- encoding: utf-8 -*-
#
# Copyright © 2017 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import os

_CONFIG = {
    "INTEGRATION_ID": None,
    "PRIVATE_KEY": None,
    "WEBHOOK_SECRET": None,
    "REQUIRED_APPROVALS": 2,
    "WEBHACK_USERNAME": None,
    "WEBHACK_PASSWORD": None,
    "DEBUG": False,
    "BASE_URL": None,
    "FLUSH_REDIS_ON_STARTUP": False,
}

print("**********************************************************")
print("configuration:")
for name, default in _CONFIG.items():
    value = os.getenv("PASTAMAKER_%s" % name, default)
    if default is not None and value is not None:
        value = type(default)(value)
    globals()[name] = value
    if (name in ["PRIVATE_KEY", "WEBHOOK_SECRET", "WEBHACK_PASSWORD"]
            and value is not None):
        value = "*****"
    print("* PASTAMAKER_%s=%s" % (name, value))
print("**********************************************************")
