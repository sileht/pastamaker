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

import requests

from pastamaker import config

LOG = logging.getLogger(__name__)

global s
s = None


def get_web_session():
    s = requests.Session()
    s.headers['User-Agent'] = (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/58.0.3029.96 Safari/537.36')
    s.trust_env = False  # Don't read netrc
    r = s.get("https://github.com/login")
    r.raise_for_status()
    m = re.search('<input name="authenticity_token" '
                  'type="hidden" value="([^"]*)" />', r.text)
    token = m.group(1)
    r = s.post("https://github.com/session",
               data={"commit": "Sign in",
                     "utf8": "✓",
                     "authenticity_token": token,
                     "login": config.WEBHACK_USERNAME,
                     "password": config.WEBHACK_PASSWORD})
    r.raise_for_status()
    return s


def web_github_get_merge_button_page(p):
    global s
    if not s:
        s = get_web_session()
    r = s.get(p.html_url + "/merge-button",
              headers={'x-requested-with': 'XMLHttpRequest',
                       'accept': 'text/html'})
    if r.status_code == 404:
        # NOTE(sileht): Maybe we got deconnected, so retry
        s = get_web_session()
        r = s.get(p.html_url + "/merge-button",
                  headers={'x-requested-with': 'XMLHttpRequest',
                           'accept': 'text/html'})
    r.raise_for_status()
    return s, r.text


def _web_github_branch_status(text):
    if '/update_branch' not in text:
        # No update_branch form
        return "dirty"
    elif 'This branch is out-of-date with the base branch' in text:
        return "behind"
    if 'This branch is up to date.' in text:
        return "clean"
    else:
        return "unknown"


def web_github_branch_status(p):
    s, text = web_github_get_merge_button_page(p)
    return _web_github_branch_status(text)


def web_github_update_branch(p):
    s, text = web_github_get_merge_button_page(p)
    state = _web_github_branch_status(text)
    if state != "behind":
        return False

    m = re.search('/update_branch" .*<input name="authenticity_token" '
                  'type="hidden" value="([^"]*)" />', text)
    if not m:
        LOG.error("PR#%s: Can't update branch, authenticity_token not found" %
                  p.number)
        return False

    token = m.group(1)
    m = re.search('<input type="hidden" name="expected_head_oid" '
                  'value="([^"]*)">', text)
    if not m:
        LOG.error("PR#%s: Can't update branch, head_oid not found" %
                  p.number)
        return False

    expected_head_oid = m.group(1)
    r = s.post(p.html_url + "/update_branch",
               headers={
                   'X-Requested-With': 'XMLHttpRequest',
                   'Content-Type': 'application/x-www-form-urlencoded; '
                   'charset=UTF-8'
               },
               data={"utf8": "✓",
                     "expected_head_oid": expected_head_oid,
                     "authenticity_token": token})
    r.raise_for_status()
    return True
