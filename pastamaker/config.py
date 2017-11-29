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
import yaml

with open("config_default.yml") as f:
    CONFIG = yaml.load(f.read())

with open("config.yml") as f:
    for key, value in dict(yaml.load(f.read())).items():
        CONFIG[key] = value

cfg_msg = ""
for name, config_value in CONFIG.items():
    name = name.upper()
    value = os.getenv("PASTAMAKER_%s" % name, config_value)
    if value == "<required>":
        raise RuntimeError("PASTAMAKER_%s environement of %s configuration"
                           "option must be set." % (name, name.lower()))
    if config_value is not None and value is not None:
        value = type(config_value)(value)
    globals()[name] = value

    if (name in ["PRIVATE_KEY", "WEBHOOK_SECRET", "WEBHACK_PASSWORD"]
            and value is not None):
        value = "*****"
    cfg_msg += "* %s: %s\n" % (name, value)

print("""
##################### CONFIGURATION ######################
%s##########################################################
""" % cfg_msg)


def get_value_from(config_options, repo, branch, default):
    login, project = repo.split("/")
    for name in ["%s@%s" % (repo, branch),
                 repo,
                 "%s/-@%s" % (login, branch),
                 "-/%s@%s" % (project, project),
                 "%s/-" % login,
                 "-/%s" % project,
                 "-@%s" % branch,
                 "default"]:
        if name in config_options:
            value = config_options[name]
            break
    else:
        value = default
    return value
