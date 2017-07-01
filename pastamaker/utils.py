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
from httplib import HTTPSConnection
import logging
import os
import sys

import daiquiri
from github import GithubException
import redis
import six
from six.moves import urllib_parse as urlparse
import ujson

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


def get_installations(integration):
    # FIXME(sileht): Need to be in github libs
    conn = HTTPSConnection("api.github.com")
    conn.request(
        method="GET",
        url="/app/installations",
        headers={
            "Authorization": "Bearer {}".format(integration.create_jwt()),
            "Accept": "application/vnd.github.machine-man-preview+json",
            "User-Agent": "PyGithub/Python"
        },
    )
    response = conn.getresponse()
    response_text = response.read()
    if six.PY3:
        response_text = response_text.decode('utf-8')
    conn.close()

    if response.status == 200:
        return ujson.loads(response_text)
    elif response.status == 403:
        raise GithubException.BadCredentialsException(
            status=response.status,
            data=response_text
        )
    elif response.status == 404:
        raise GithubException.UnknownObjectException(
            status=response.status,
            data=response_text
        )
    raise GithubException.GithubException(
        status=response.status,
        data=response_text
    )


def get_installation_id(integration, owner):
    installations = get_installations(integration)
    for install in installations:
        if install["account"]["login"] == owner:
            return install["id"]
