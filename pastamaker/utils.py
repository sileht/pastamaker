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

import hashlib
import hmac
import logging
import os
import sys
import urlparse

import daiquiri
import redis

from pastamaker import config

LOG = logging.getLogger(__name__)


global REDIS_CONNECTION
REDIS_CONNECTION = None


def get_redis():
    global REDIS_CONNECTION

    if REDIS_CONNECTION is None:
        redis_url = os.getenv('REDISTOGO_URL')
        urlparse.uses_netloc.append('redis')
        url = urlparse.urlparse(redis_url)
        REDIS_CONNECTION = redis.Redis(
            host=url.hostname, port=url.port,
            db=0, password=url.password)
    return REDIS_CONNECTION


def setup_logging():
    daiquiri.setup(
        outputs=[daiquiri.output.Stream(
            sys.stdout,
            formatter=logging.Formatter("%(levelname)s %(name)s: %(message)s"),
        )],
        level=(logging.DEBUG if config.DEBUG else logging.INFO),
    )
    daiquiri.set_default_log_levels([("rq", "ERROR")])


def compute_hmac(data):
    mac = hmac.new(config.WEBHOOK_SECRET, msg=data, digestmod=hashlib.sha1)
    return str(mac.hexdigest())
