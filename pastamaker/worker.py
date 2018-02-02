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
from pastamaker import gh_pr
from pastamaker import utils

LOG = logging.getLogger(__name__)

QUEUES = None
MAX_FAILURES = 3


def event_handler(event_type, data):
    """Everything start here"""

    integration = github.GithubIntegration(config.INTEGRATION_ID,
                                           config.PRIVATE_KEY)
    token = integration.get_access_token(data["installation"]["id"]).token
    g = github.Github(token)
    try:
        user = g.get_user(data["repository"]["owner"]["login"])
        repo = user.get_repo(data["repository"]["name"])

        engine.PastaMakerEngine(g, user, repo).handle(event_type, data)
    except github.RateLimitExceededException:
        LOG.error("rate limit reached")

def retry_handler(job, *exc_info):
    job.meta.setdefault('failures', 0)
    job.meta['failures'] += 1

    # Too many failures
    if job.meta['failures'] >= MAX_FAILURES:
        LOG.warn('job %s: failed too many times times - moving to failed queue' % job.id)
        job.save()
        return True

    # Requeue job and stop it from being moved into the failed queue
    LOG.warn('job %s: failed %d times - retrying' % (job.id, job.meta['failures']))

    for queue in QUEUES:
        if queue.name == job.origin:
            queue.enqueue_job(job, timeout=job.timeout)
            return False

    # Can't find queue, which should basically never happen as we only work jobs that match the given queue names and
    # queues are transient in rq.
    LOG.warn('job %s: cannot find queue %s - moving to failed queue' % (job.id, job.origin))
    return True


def main():
    utils.setup_logging()
    config.log()
    gh_pr.monkeypatch_github()
    if config.FLUSH_REDIS_ON_STARTUP:
        utils.get_redis().flushall()
    with rq.Connection(utils.get_redis()):
	QUEUES = [rq.Queue('default')]
        worker = rq.worker.HerokuWorker(
            QUEUES, exception_handlers=[retry_handler])
        worker.work()


if __name__ == '__main__':
    main()
