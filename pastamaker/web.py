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

import hmac
import logging
import os

import flask
import github
import rq
import ujson

from pastamaker import config
from pastamaker import utils
from pastamaker import worker


LOG = logging.getLogger(__name__)

app = flask.Flask(__name__)


def get_redis():
    if not hasattr(flask.g, 'redis'):
        conn = utils.get_redis()
        flask.g.redis = conn
    return flask.g.redis


def get_queue():
    if not hasattr(flask.g, 'rq_queue'):
        flask.g.rq_queue = rq.Queue(connection=get_redis())
    return flask.g.rq_queue


@app.route("/auth", methods=["GET"])
def auth():
    return "pastamaker don't need oauth setup"


@app.route("/refresh/<owner>/<repo>/<path:branch>",
           methods=["POST"])
def force_refresh(owner, repo, branch):
    authentification()

    integration = github.GithubIntegration(config.INTEGRATION_ID,
                                           config.PRIVATE_KEY)

    installation_id = utils.get_installation_id(integration, owner)
    if not installation_id:
        flask.abort(404, "%s have not installed pastamaker" % owner)

    # Mimic the github event format
    data = {
        'repository': {
            'name': repo,
            'full_name': '%s/%s' % (owner, repo),
            'owner': {'login': owner},
        },
        'installation': {'id': installation_id},
        "branch": branch,
    }
    get_queue().enqueue(worker.event_handler, "refresh", data)
    return "", 202


@app.route("/queue/<owner>/<repo>/<path:branch>")
def queue(owner, repo, branch):
    return get_redis().get("queues|%s|%s|%s" % (owner, repo, branch)) or "[]"


@app.route("/status")
def status():
    r = get_redis()
    queues = []
    for key in r.keys("queues|*|*|*"):
        LOG.error(key)
        _, owner, repo, branch = key.split("#")
        pulls = ujson.loads(r.get(key) or "[]")
        queues.append({
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "pulls": pulls,
        })
    return ujson.dumps(queues)


@app.route("/event", methods=["POST"])
def event_handler():
    authentification()

    event_type = flask.request.headers.get("X-GitHub-Event")
    event_id = flask.request.headers.get("X-GitHub-Delivery")
    data = flask.request.get_json()

    if event_type in ["refresh", "pull_request", "status",
                      "pull_request_review"]:
        get_queue().enqueue(worker.event_handler, event_type, data)

    if "repository" in data:
        repo_name = data["repository"]["full_name"]
    else:
        repo_name = data["installation"]["account"]["login"]

    LOG.info('[%s/%s] received "%s" event "%s"',
             data["installation"]["id"], repo_name,
             event_type, event_id)

    return "", 202


@app.route("/")
def index():
    return flask.send_file(os.path.join("static", "index.html"))


@app.route("/favicon.ico")
def favicon():
    return flask.send_file(os.path.join("static", "favicon.ico"))


def authentification():
    # Only SHA1 is supported
    header_signature = flask.request.headers.get('X-Hub-Signature')
    if header_signature is None:
        LOG.warning("Webhook without signature")
        flask.abort(403)

    try:
        sha_name, signature = header_signature.split('=')
    except ValueError:
        sha_name = None

    if sha_name != 'sha1':
        LOG.warning("Webhook signature malformed")
        flask.abort(403)

    mac = utils.compute_hmac(flask.request.data)
    if not hmac.compare_digest(mac, str(signature)):
        LOG.warning("Webhook signature invalid")
        flask.abort(403)
