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
import os
import shutil
import subprocess
import sys
import tempfile

import github
import requests

from pastamaker import config

LOG = logging.getLogger(__name__)

NULL = file(os.devnull, 'wb')

class Gitter(object):
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="pastamaker-gitter")
        LOG.info("working in: %s" % self.tmp)

    def __call__(self, *args, **kwargs):
        LOG.info("calling: %s" % " ".join(args))
        kwargs["cwd"] = self.tmp
        kwargs.setdefault("stdout", NULL)
        p = subprocess.Popen(["git"] + list(args), **kwargs)
        p.wait()
        return p

    def cleanup(self):
        LOG.info("cleaning: %s" % self.tmp)
        shutil.rmtree(self.tmp)


def update_branch(self, token, merge=True):
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

    git = Gitter()
    try:
        git("clone", "--depth=%d" % (int(self.commits) + 1),
            "-b", self.head.ref,
            "https://%s@github.com/%s/" % (token, self.head.repo.full_name), ".")
        git("remote", "add", "upstream",
            "https://%s@github.com/%s.git" % (token, self.base.repo.full_name))
        git("config", "user.name", "Mergify")
        git("config", "user.email", "noreply@mergify.io")

        p = git("log", "--pretty='format:%cI'", stdout=subprocess.PIPE)
        last_commit_date = p.stdout.read().split("\n")[-1]

        git("fetch", "upstream", self.base.ref,
            "--shallow-since='%s'" % last_commit_date)
        if merge:
            git("merge", "upstream/%s" % self.base.ref, "-m", "Merge branch '%s' into '%s'" % (self.base.ref, self.head.ref))
        else:
            git("rebase", "upstream/%s" % self.base.ref)
        git("push", "origin", self.head.ref)
    except Exception:
        LOG.exception("git rebase fail")
        return False
    finally:
        git.cleanup()
    return True


def test():
    from pastamaker import gh_pr
    from pastamaker import utils

    utils.setup_logging()
    config.log()
    gh_pr.monkeypatch_github()


    parts = sys.argv[1].split("/")
    LOG.info("Getting repo %s ..." % sys.argv[1])

    if True:
        # With access_token got from oauth
        token = sys.argv[2]

        g = github.Github(token)
        user = g.get_user(parts[3])
        repo = user.get_repo(parts[4])
        pull = repo.get_pull(int(parts[6]))
        update_branch(pull, token)
    else:
        # With access_token got from integration
        integration = github.GithubIntegration(config.INTEGRATION_ID,
                                               config.PRIVATE_KEY)

        installation_id = utils.get_installation_id(integration, parts[3])
        token = integration.get_access_token(installation_id).token
        update_branch(pull, "x-access-token:%s" % token)


if __name__ == '__main__':
    test()