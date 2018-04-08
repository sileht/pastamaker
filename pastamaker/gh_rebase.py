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

from datetime import datetime
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
    import github

    from pastamaker import gh_pr
    from pastamaker import utils

    utils.setup_logging()
    config.log()
    gh_pr.monkeypatch_github()

    integration = github.GithubIntegration(config.INTEGRATION_ID,
                                           config.PRIVATE_KEY)

    installation_id = utils.get_installation_id(integration, "sileht")
    token = integration.get_access_token(installation_id).token
    g = github.Github(token)
    user = g.get_user("sileht")
    repo = user.get_repo("repotest")
    pull = repo.get_pull(2)
    ref = repo.get_git_ref("heads/%s" % pull.base.ref)
    print("%s head: %s" % (pull.base.ref, ref.object.sha))
    print("pull base: %s" % (pull.base.sha))

    if (ref.object.sha == pull.base.sha):
        return

    pull_head = repo.get_git_commit(pull.head.sha)

    forked_branch_head = repo.get_git_commit(ref.object.sha)

    author = github.InputGitAuthor(
        "mergify.io", "sileht-mergify@sileht.net",
        "%sZ" % datetime.now().isoformat())

    print(pull_head)
    print(pull_head.tree)
    print(forked_branch_head)
    print(forked_branch_head.message)
    print(forked_branch_head.tree)

    last_commit = repo.create_git_commit(
        message="Merge branch '%s' into %s" % (pull.base.ref, pull.head.ref),
        tree=pull_head.tree,
        parents=[pull_head, forked_branch_head],
        author=author,
        committer=author
    )

    forked_repo = pull.get_repo(pull.head.repo.name)
    forked_branch_ref = forked_repo.get_git_ref("heads/%s" % pull.head.ref)
    print(forked_branch_ref.url)
    print(last_commit.sha)
    forked_branch_ref.edit(last_commit.sha, force=True)


if __name__ == '__main__':
    test()
