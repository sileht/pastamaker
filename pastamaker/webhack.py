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
import re
import sys

import requests

from pastamaker import config

LOG = logging.getLogger(__name__)

global global_session
global_session = None


class ParsingError(Exception):
    pass


def get_authencity_token(text):
    m = re.search('name="authenticity_token"[^>]*value="([^"]*)" />',
                  text.replace("\n", ""))
    if not m:
        raise ParsingError("Authencity token not found")
    return m.group(1)


def get_last_modified(text):
    m = re.search('data-last-modified="([^"]*)"', text.replace("\n", ""))
    if not m:
        raise ParsingError("data-last-modified not found")
    return m.group(1)


def get_web_session(force=False):
    global global_session
    if not global_session or force:
        global_session = requests.Session()
        global_session.headers['User-Agent'] = (
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/64.0.3282.119 Safari/537.36')
        global_session.trust_env = False  # Don't read netrc

        r = global_session.get("https://github.com/login")
        r.raise_for_status()
        token = get_authencity_token(r.text)
        r = global_session.post("https://github.com/session",
                                data={"commit": "Sign+in",
                                      "utf8": "✓",
                                      "authenticity_token": token,
                                      "login": config.WEBHACK_USERNAME,
                                      "password": config.WEBHACK_PASSWORD})
        r.raise_for_status()
    return global_session


def _web_github_update_branch(p):
    s = get_web_session()

    # get the PR to set some useful cookie
    r = s.get(p.html_url + "/merge-button")
    r.raise_for_status()

    # Ensure we can click on the btn
    if 'This branch is out-of-date with the base branch' not in r.text:
        LOG.error("PR#%s: Can't update branch, state is not behind", p.number)
        return False

    # Click on the Update btn
    token = get_authencity_token(r.text)
    r = s.post(p.html_url + "/update_branch", data={
        "utf8": "✓",
        "authenticity_token": token,
        "expected_head_oid": p.head.sha,
    }, headers={'x-requested-with': 'XMLHttpRequest'})
    r.raise_for_status()
    return True


def web_github_update_branch(p):
    try:
        return _web_github_update_branch(p)
    except ParsingError as e:
        LOG.error("PR#%s: Can't update branch: %s",
                  p.number, e)
        return False


def test():
    import github

    from pastamaker import gh_pr
    from pastamaker import utils

    utils.setup_logging()
    config.log()
    gh_pr.monkeypatch_github()

    parts = sys.argv[1].split("/")

    LOG.info("Getting pull request...")
    g = github.Github()
    user = g.get_user(parts[3])
    repo = user.get_repo(parts[4])
    p = repo.get_pull(int(parts[6]))
    LOG.info("Pushing update button...")
    LOG.info(web_github_update_branch(p))


if __name__ == '__main__':
    test()
