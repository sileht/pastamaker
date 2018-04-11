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
import subprocess
import sys
import tempfile

import github
import requests

from pastamaker import config

LOG = logging.getLogger(__name__)

STEP1_URL = "https://github.com/login/oauth/authorize"
STEP2_URL = "https://gh.mergify.io/connected"
STEP3_URL = "https://github.com/login/oauth/access_token"


def get_oauth_access_token():
    r = requests.get(STEP1_URL, params=dict(
        client_id=config.OAUTH_CLIENT_ID,
        redirect_uri=STEP2_URL,
        scope="repo",
        state="randomizeme",
    ), allow_redirects=False)
    print(r.headers['Location'])
    code = input("Enter code")

    r = requests.post(STEP3_URL, params=dict(
        client_id=config.OAUTH_CLIENT_ID,
        client_secret=config.OAUTH_CLIENT_SECRET,
        code=code,
    ), headers={'Accept': 'application/json'})
    return r.json()['access_token']


def test():
    from pastamaker import gh_pr
    from pastamaker import utils

    utils.setup_logging()
    config.log()
    gh_pr.monkeypatch_github()

    token = sys.argv[1]

    rebase(token, "sileht", "repotest", 2)


class Gitter(object):
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="pastamaker-gitter")

    def __call__(self, *args, **kwargs):
        kwargs["cwd"] = self.tmp
        p = subprocess.Popen(*args, **kwargs)
        p.wait()
        return p.stdout, p.stderr


def rebase(token, user, repo, pull_number):
    # NOTE(sileht):
    # $ curl https://api.github.com/repos/sileht/repotest/pulls/2 | jq .commits
    # 2
    # $ git clone https://XXXXX@github.com/sileht-tester/repotest \
    #           --depth=$((2 + 1)) -b sileht/testpr
    # $ cd repotest
    # $ git remote add upstream https://XXXXX@github.com/sileht/repotest.git
    # $ git log | grep Date | tail -1
    # Date:   Fri Mar 30 21:30:26 2018 (10 days ago)
    # $ git fetch upstream master --shallow-since="Fri Mar 30 21:30:26 2018"
    # $ git rebase upstream/master
    # $ git push origin sileht/testpr:sileht/testpr

    g = github.Github(token)
    pull = g.get_user(user).get_repo(repo).get_pull(2)

    git = Gitter()
    try:
        git("clone", "--depth=%d" % (int(pull.commits) + 1),
            "-b", pull.ref,
            "https://%s@github.com/%s/" % (token, pull.head.full_name), ".")
        git("remote", "add",
            "https://%s@github.com/%s.git" % (token, pull.base.full_name))

        last_commit_date = git("log", "--pretty='format:%cI'",
                               stdout=subprocess.PIPE).split("\n")[-1]

        git("fetch", "upstream", pull.base.ref,
            "--shallow-since='%s'" % last_commit_date)
        git("rebase", "upstream/%s" % pull.base.ref)
        git("push", "origin", pull.head.full_name)
    finally:
        git.cleanup()


if __name__ == '__main__':
    test()
