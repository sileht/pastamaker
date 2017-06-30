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
from httplib import HTTPSConnection
import logging

import flask
import github
from github import GithubException
import rq
import six
import ujson

from pastamaker import config
from pastamaker import engine
from pastamaker import utils
from pastamaker import worker


LOG = logging.getLogger(__name__)

app = flask.Flask(__name__)


def get_queue():
    if not hasattr(flask.g, 'rq_queue'):
        conn = utils.get_redis()
        flask.g.rq_queue = rq.Queue(connection=conn)
    return flask.g.rq_queue


@app.route("/", methods=["GET"])
def hello():
    return "Welcome to pastamaker"


@app.route("/auth", methods=["GET"])
def auth():
    return "pastamaker don't need oauth setup"


@app.route("/refresh/<installation_id>/<owner>/<repo>/<path:branch>",
           methods=["POST"])
def force_refresh(installation_id, owner, repo, branch):
    authentification()

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


@app.route("/queue/<owner>/<repo>/<path:branch>")
def queue(owner, repo, branch):
    integration = github.GithubIntegration(config.INTEGRATION_ID,
                                           config.PRIVATE_KEY)

    installations = get_installations(integration)
    for install in installations:
        if install["account"]["login"] == owner:
            installation_id = install["id"]
            break
    else:
        flask.abort(404, "%s have not installed pastamaker" % owner)

    token = integration.get_access_token(installation_id).token
    g = github.Github(token)
    user = g.get_user(owner)
    repo = user.get_repo(repo)

    e = engine.PastaMakerEngine(g, user, repo)
    pending = e.pending_pulls[branch]
    try:
        pulls = e.get_pull_requests_queue(branch)
    except GithubException as e:
        if e.status == 403:
            flask.abort(404, "%s have not installed pastamaker" % owner)
        raise

    pulls = [p for p in pulls if p.number != pending.number]
    pulls.insert(0, pending)
    return ujson.dumps([p.raw_data for p in pulls])


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
        repo_name = data["repository"]["full_name"],
    else:
        repo_name = data["installation"]["account"]["login"]

    LOG.info('[%s/%s] received "%s" event "%s"',
             data["installation"]["id"], repo_name,
             event_type, event_id)

    return "", 202


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
