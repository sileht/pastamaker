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

from pastamaker import config

LOG = logging.getLogger(__name__)


def is_protected(g_repo, branch, enforce_admins, contexts):
    g_branch = g_repo.get_branch(branch)
    if not g_branch.protected:
        return False

    headers, data = g_repo._requester.requestJsonAndCheck(
        "GET", g_repo.url + "/branches/" + branch + '/protection',
        headers={'Accept': 'application/vnd.github.v3+json'}
    )

    # NOTE(sileht): delete urls from the payload
    del data['url']
    del data["required_status_checks"]["url"]
    del data["required_status_checks"]["contexts_url"]
    del data["required_pull_request_reviews"]["url"]
    del data["enforce_admins"]["url"]
    data["required_status_checks"]["contexts"] = sorted(
        data["required_status_checks"]["contexts"])

    expected = {
        'required_pull_request_reviews': {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
        },
        'required_status_checks': {
            'strict': True,
            'contexts': sorted(contexts),
        },
        'enforce_admins': {
            "enabled": enforce_admins
        }
    }

    return expected == data


def protect(g_repo, branch, enforce_admins, contexts):
    p = {
        'required_pull_request_reviews': {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
        },
        'required_status_checks': {
            'strict': True,
            'contexts': contexts,
        },
        'restrictions': None,
        'enforce_admins': enforce_admins,
    }

    if g_repo.organization:
        p['required_pull_request_reviews']['dismissal_restrictions'] = {}

    # NOTE(sileht): Not yet part of the API
    # maybe soon https://github.com/PyGithub/PyGithub/pull/527
    g_repo._requester.requestJsonAndCheck(
        'PUT',
        "{base_url}/branches/{branch}/protection".format(base_url=g_repo.url,
                                                         branch=branch),
        input=p,
        headers={'Accept': 'application/vnd.github.v3+json'}
    )


def protect_if_needed(g_repo, branch):
    enforce_admins = config.get_value_from(
        config.BRANCH_PROTECTION_ENFORCE_ADMINS,
        g_repo.full_name, branch, True)
    contexts = config.get_value_from(
        config.BRANCH_PROTECTION_CONTEXTS,
        g_repo.full_name, branch, True)
    if not is_protected(g_repo, branch, enforce_admins, contexts):
        LOG.warning("Branch %s of %s is misconfigured, configuring it",
                    branch, g_repo.full_name)
        protect(g_repo, branch, enforce_admins, contexts)
