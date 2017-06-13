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


import logging

import github
import rq
import rq.worker

from pastamaker import config
from pastamaker import engine
from pastamaker import pr
from pastamaker import utils

LOG = logging.getLogger(__name__)


def event_handler(event_type, data):
    """Everything start here"""

    integration = github.GithubIntegration(config.INTEGRATION_ID,
                                           config.PRIVATE_KEY)
    token = integration.get_access_token(data["installation"]["id"]).token
    g = github.Github(token)

    user = g.get_user(data["repository"]["owner"]["login"])
    repo = user.get_repo(data["repository"]["name"])

    engine.PastaMakerEngine(g, user, repo).handle(event_type, data)


def error_handler(job, *exc_info):
    LOG.error("event handler failure", exc_info=exc_info)


def main():
    utils.setup_logging()
    pr.monkeypatch_github()
    if config.FLUSH_REDIS_ON_STARTUP:
        utils.get_redis().flushall()
    with rq.Connection(utils.get_redis()):
        worker = rq.worker.HerokuWorker([rq.Queue('default')],
                                        exception_handlers=[error_handler])
        worker.work()


if __name__ == '__main__':
    main()
