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

import copy
import logging
import time

import github
import requests
import six.moves

from pastamaker import config

LOG = logging.getLogger(__name__)
TRAVIS_BASE_URL = 'https://api.travis-ci.org'
TRAVIS_V2_HEADERS = {"Accept": "application/vnd.travis-ci.2+json",
                     "User-Agent": "Pastamaker/1.0.0"}

UNUSABLE_STATES = ["unknown", None]


def ensure_mergable_state(pull):
    if pull.is_merged() or pull.mergeable_state not in UNUSABLE_STATES:
        return pull

    # Github is currently processing this PR, we wait the completion
    for i in range(0, 5):
        LOG.info("%s, refreshing...", pull.pretty())
        pull.update()
        if pull.is_merged() or pull.mergeable_state not in UNUSABLE_STATES:
            break
        time.sleep(0.42)  # you known, this one always work

    LOG.info("%s, refreshed", pull.pretty())
    return pull


def compute_travis_detail(pull):
    if (not pull.pastamaker["travis_url"] or
            pull.pastamaker["travis_url"] == "#"):
        return None
    build_id = pull.pastamaker["travis_url"].split("?")[0].split("/")[-1]
    r = requests.get(TRAVIS_BASE_URL + "/builds/" + build_id,
                     headers=TRAVIS_V2_HEADERS)
    if r.status_code != 200:
        return None
    build = r.json()["build"]
    build["resume_state"] = pull.pastamaker["travis_state"]
    build["jobs"] = []
    for job_id in build["job_ids"]:
        r = requests.get(TRAVIS_BASE_URL + "/jobs/%s" % job_id,
                         headers=TRAVIS_V2_HEADERS)
        if r.status_code == 200:
            job = r.json()["job"]
            job["log_url"] = TRAVIS_BASE_URL + "/jobs/%s/log" % job_id
            LOG.debug("%s: job %s %s -> %s" % (pull.pretty(), job_id,
                                               job["state"],
                                               job["log_url"]))
            build["jobs"].append(job)
            if (pull.pastamaker["travis_state"] == "pending" and
                    job["state"] == "started"):
                build["resume_state"] = "working"
    LOG.debug("%s: build %s %s/%s" % (pull.pretty(), build_id,
                                      build["state"],
                                      build["resume_state"]))
    return build


def compute_approvals(pull):
    allowed = [u.id for u in pull.base.repo.get_collaborators()]

    users_info = {}
    reviews_ok = set()
    reviews_ko = set()
    for review in pull.get_reviews():
        if review.user.id not in allowed:
            continue

        users_info[review.user.login] = review.user.raw_data
        if review.state == 'APPROVED':
            reviews_ok.add(review.user.login)
            if review.user.login in reviews_ko:
                reviews_ko.remove(review.user.login)

        elif review.state in ["DISMISSED", "CHANGES_REQUESTED"]:
            if review.user.login in reviews_ok:
                reviews_ok.remove(review.user.login)
            if review.user.login in reviews_ko:
                reviews_ko.remove(review.user.login)
            if review.state == "CHANGES_REQUESTED":
                reviews_ko.add(review.user.login)
        elif review.state == 'COMMENTED':
            pass
        else:
            LOG.error("%s FIXME review state unhandled: %s",
                      pull.pretty(), review.state)

    required = config.get_value_from(config.REQUIRED_APPROVALS,
                                     pull.base.repo.full_name,
                                     pull.base.ref, 2)
    # FIXME(sileht): Compute the thing on JS side
    remaining = list(six.moves.range(max(0, required - len(reviews_ok))))
    return ([users_info[u] for u in reviews_ok],
            [users_info[u] for u in reviews_ko],
            required, remaining)


def compute_ci_statuses(pull):
    commit = pull.base.repo.get_commit(pull.head.sha)
    statuses = {}
    # NOTE(sileht): Statuses are returned in reverse chronological order.
    # The first status in the list will be the latest one.
    for s in reversed(list(commit.get_statuses())):
        statuses[s.context] = {"state": s.state, "url": s.target_url}
    return statuses


def compute_approved(pull):
    approved = len(pull.pastamaker["approvals"][0])
    requested_changes = len(pull.pastamaker['approvals'][1])
    required = pull.pastamaker['approvals'][2]
    if requested_changes != 0:
        return False
    else:
        return approved >= required


def compute_travis_state(pull):
    return pull.pastamaker["ci_statuses"].get(
        "continuous-integration/travis-ci/pr", {"state": "unknown"}
    )["state"]


def compute_travis_url(pull):
    return pull.pastamaker["ci_statuses"].get(
        "continuous-integration/travis-ci/pr", {"url": "#"}
    )["url"]


def compute_weight(pull):
    if not pull.pastamaker["approved"]:
        weight = -1
    elif (pull.mergeable_state in ["clean", "unstable"]
          and pull.pastamaker["travis_state"] == "success"
          and pull.pastamaker["sync_with_master"]):
        # Best PR ever, up2date and CI OK
        weight = 11
    elif pull.mergeable_state in ["clean", "unstable"]:
        weight = 10
    elif (pull.mergeable_state == "blocked"
          and pull.pastamaker["sync_with_master"]
          and pull.pastamaker["travis_state"] == "pending"):
        # Maybe clean soon, or maybe this is the previous run
        # selected PR that we just rebase
        weight = 10
    elif (pull.mergeable_state == "behind"
          and not pull.pastamaker["sync_with_master"]):
        # Not up2date, but ready to merge, is branch updatable
        if pull.pastamaker["travis_state"] == "success":
            weight = 7
        elif pull.pastamaker["travis_state"] == "pending":
            weight = 5
        else:
            weight = -1
    else:
        weight = -1
    if weight >= 0 and pull.milestone is not None:
        weight += 1
    # LOG.info("%s prio: %s, %s, %s, %s, %s", pull.pretty(), weight,
    #          pull.pastamaker["approved"], pull.mergeable_state,
    #          pull.pastamaker["travis_state"],
    #          pull.pastamaker["sync_with_master"])
    return weight


def compute_sync_with_mater(pull):
    branch = pull.base.repo.get_branch(pull.base.ref)
    return pull.base.sha == branch.commit.sha


def compute_raw_data(pull):
    data = copy.copy(pull.raw_data)
    data["pastamaker_ci_statuses"] = pull.pastamaker["ci_statuses"]
    data["pastamaker_weight"] = pull.pastamaker["weight"]
    data["pastamaker_sync_with_master"] = \
        pull.pastamaker["sync_with_master"]
    data["pastamaker_commits"] = [c.raw_data for c in
                                  pull.pastamaker["commits"]]
    data["pastamaker_travis_state"] = pull.pastamaker["travis_state"]
    data["pastamaker_travis_url"] = pull.pastamaker["travis_url"]
    data["pastamaker_travis_detail"] = pull.pastamaker["travis_detail"]
    data["pastamaker_approvals"] = pull.pastamaker["approvals"]
    data["pastamaker_approved"] = pull.pastamaker["approved"]
    return data


def cache_hook_commits(pull, cache):
    return [github.Commit.Commit(pull.base.repo._requester, {}, raw_commit,
                                 completed=True)
            for raw_commit in cache]


# Order matter, some method need result of some other
FULLIFIER = [
    ("commits", lambda p: list(p.get_commits())),
    ("sync_with_master", compute_sync_with_mater),
    ("approvals", compute_approvals),
    ("approved", compute_approved),            # Need approvals
    ("ci_statuses", compute_ci_statuses),      # Need approvals
    ("travis_state", compute_travis_state),    # Need ci_statuses
    ("travis_url", compute_travis_url),        # Need ci_statuses
    ("travis_detail", compute_travis_detail),  # Need travis_url
    ("weight", compute_weight),                # Need approved, travis_state
    ("raw_data", compute_raw_data),            # Need everything
]

CACHE_HOOK = {
    "commits": cache_hook_commits,
}


def fullify(pull, cache=None):
    if not hasattr(pull, "pastamaker"):
        pull.pastamaker = {"fullified": False}

    pull = ensure_mergable_state(pull)

    for key, method in FULLIFIER:
        if key not in pull.pastamaker:
            if cache and "pastamaker_%s" % key in cache:
                value = cache["pastamaker_%s" % key]
                if key in CACHE_HOOK:
                    value = CACHE_HOOK[key](pull, value)
            elif cache and key == "raw_data":
                value = dict((k, v) for k, v in cache.items()
                             if not k.startswith("pastamaker_"))
            else:
                LOG.info("%s, begin computing %s" % (pull.pretty(), key))
                value = method(pull)
                LOG.info("%s, end computing %s" % (pull.pretty(), key))
            pull.pastamaker[key] = value

    pull.pastamaker["fullified"] = True
    return pull
