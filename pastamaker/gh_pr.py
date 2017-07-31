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
import six.moves

from pastamaker import config
# from pastamaker import gh_commit
from pastamaker import webhack

LOG = logging.getLogger(__name__)


def pretty(self):
    return "%s/%s/pull/%s@%s (%s/%s/%s/%s)" % (
        self.base.user.login,
        self.base.repo.name,
        self.number,
        self.base.ref,
        self.mergeable_state or "none",
        self.travis_state,
        len(self.approvals[0]),
        self.pastamaker_weight if self.pastamaker_weight >= 0 else "NA",
    )


@property
def approvals(self):
    if not hasattr(self, "_pastamaker_approvals"):
        allowed = [u.id for u in self.base.repo.get_collaborators()]

        users_info = {}
        reviews_ok = set()
        reviews_ko = set()
        for review in self.get_reviews():
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
                          self.pretty(), review.state)

        required = config.get_value_from(config.REQUIRED_APPROVALS,
                                         self.base.repo.full_name,
                                         self.base.ref, 2)
        # FIXME(sileht): Compute the thing on JS side
        remaining = list(six.moves.range(max(0, required - len(reviews_ok))))
        self._pastamaker_approvals = ([users_info[u] for u in reviews_ok],
                                      [users_info[u] for u in reviews_ko],
                                      required, remaining)
    return self._pastamaker_approvals


def pastamaker_update_status(self):
    approved = len(self.approvals[0])
    requested_changes = len(self.approvals[1])
    required = self.approvals[2]
    if requested_changes != 0:
        state = "failure"
        description = "%s changes requested" % requested_changes
    else:
        state = "success" if approved >= required else "pending"
        description = "%s of %s required reviews" % (approved, required)

    commit = self.base.repo.get_commit(self.head.sha)
    for s in commit.get_statuses():
        if s.context == "pastamaker/reviewers":
            need_update = (s.state != state or
                           s.description != description)
            break
    else:
        need_update = True

    if need_update:
        # NOTE(sileht): We can't use commit.create_status() because
        # if use the head repo instead of the base repo
        try:
            self._requester.requestJsonAndCheck(
                "POST",
                self.base.repo.url + "/statuses/" + self.head.sha,
                input={'state': state,
                       'description': description,
                       'context': "pastamaker/reviewers"},
                headers={'Accept':
                         'application/vnd.github.machine-man-preview+json'}
            )
        except github.GithubException as e:
            LOG.exception("%s set status fail: %s",
                          self.pretty(), e.data["message"])
    return need_update


@property
def pastamaker_ci_statuses(self):
    if not hasattr(self, "_pastamaker_ci_statuses"):
        commit = self.base.repo.get_commit(self.head.sha)
        statuses = {}
        # NOTE(sileht): Statuses are returned in reverse chronological order.
        # The first status in the list will be the latest one.
        for s in reversed(list(commit.get_statuses())):
            statuses[s.context] = {"state": s.state, "url": s.target_url}
        self._pastamaker_ci_statuses = statuses
    return self._pastamaker_ci_statuses


@property
def pastamaker_raw_data(self):
    data = copy.deepcopy(self.raw_data)
    data["pastamaker_ci_statuses"] = self.pastamaker_ci_statuses
    data["pastamaker_weight"] = self.pastamaker_weight
    data["travis_state"] = self.travis_state
    data["travis_url"] = self.travis_url
    data["approvals"] = self.approvals
    data["pastamaker_commits"] = [c.raw_data for c in self.pastamaker_commits]
    return data


@property
def approved(self):
    approved = len(self.approvals[0])
    requested_changes = len(self.approvals[1])
    required = self.approvals[2]
    if requested_changes != 0:
        return False
    else:
        return approved >= required


@property
def travis_state(self):
    return self.pastamaker_ci_statuses.get(
        "continuous-integration/travis-ci/pr", {"state": "unknown"}
    )["state"]


@property
def travis_url(self):
    return self.pastamaker_ci_statuses.get(
        "continuous-integration/travis-ci/pr", {"url": "#"}
    )["url"]


@property
def pastamaker_weight(self):
    if not hasattr(self, "_pastamaker_weight"):
        if not self.approved:
            weight = -1
        elif (self.mergeable_state == "clean"
              and self.travis_state == "success"
              and self.update_branch_state == "clean"):
            # Best PR ever, up2date and CI OK
            weight = 11
        elif self.mergeable_state == "clean":
            weight = 10
        elif (self.mergeable_state == "blocked"
              and self.travis_state == "pending"
              and self.update_branch_state == "clean"):
            # Maybe clean soon, or maybe this is the previous run
            # selected PR that we just rebase
            weight = 10
        elif (self.mergeable_state == "behind"
              and self.update_branch_state not in ["unknown", "dirty"]):
            # Not up2date, but ready to merge, is branch updatable
            if self.travis_state == "success":
                weight = 7
            elif self.travis_state == "pending":
                weight = 5
            else:
                weight = -1
        else:
            weight = -1
        self._pastamaker_weight = weight
        # LOG.info("%s prio: %s, %s, %s, %s, %s", self.pretty(), weight,
        #          self.approved, self.mergeable_state, self.travis_state,
        #          self.update_branch_state)
    return self._pastamaker_weight


def pastamaker_update(self, force=False):
    for attr in ["_pastamaker_commits",
                 "_pastamaker_weight",
                 "_pastamaker_ci_statuses",
                 "_pastamaker_approvals"]:
        if hasattr(self, attr):
            delattr(self, attr)

    if not force and self.mergeable_state not in ["unknown", None]:
        return self

    # Github is currently processing this PR, we wait the completion
    while True:
        LOG.debug("%s, refreshing...", self.pretty())
        self.update()
        if self.mergeable_state not in ["unknown", None]:
            break
        time.sleep(0.042)  # you known, this one always work

    LOG.debug("%s, refreshed", self.pretty())
    return self


@property
def pastamaker_commits(self):
    if not hasattr(self, "_pastamaker_commits"):
        self._pastamaker_commits = list(self.get_commits())
    return self._pastamaker_commits


def pastamaker_merge(self, **post_parameters):
    post_parameters["sha"] = self.head.sha
    # FIXME(sileht): use self.merge when it will
    # support sha and merge_method arguments
    try:
        post_parameters['merge_method'] = "rebase"
        headers, data = self._requester.requestJsonAndCheck(
            "PUT", self.url + "/merge", input=post_parameters)
        return github.PullRequestMergeStatus.PullRequestMergeStatus(
            self._requester, headers, data, completed=True)
    except github.GithubException as e:
        if e.data["message"] != "This branch can't be rebased":
            LOG.exception("%s merge fail: %d, %s",
                          self.pretty(), e.status, e.data["message"])
            return

        # If rebase fail retry with merge
        post_parameters['merge_method'] = "merge"
        try:
            headers, data = self._requester.requestJsonAndCheck(
                "PUT", self.url + "/merge", input=post_parameters)
            return github.PullRequestMergeStatus.PullRequestMergeStatus(
                self._requester, headers, data, completed=True)
        except github.GithubException as e:
            LOG.exception("%s merge fail: %d, %s",
                          self.pretty(), e.status, e.data["message"])

        # FIXME(sileht): depending on the kind of failure we can endloop
        # to try to merge the pr again and again.
        # to repoduce the issue


def from_event(repo, data):
    # TODO(sileht): do it only once in handle()
    # NOTE(sileht): Convert event payload, into pygithub object
    # instead of querying the API
    if "pull_request" in data:
        return github.PullRequest.PullRequest(
            repo._requester, {}, data["pull_request"], completed=True)


def monkeypatch_github():
    p = github.PullRequest.PullRequest

    p.pretty = pretty
    p.travis_state = travis_state
    p.travis_url = travis_url
    p.approved = approved
    p.approvals = approvals

    p.pastamaker_update = pastamaker_update
    p.pastamaker_merge = pastamaker_merge
    p.pastamaker_update_status = pastamaker_update_status

    p.pastamaker_commits = pastamaker_commits
    p.pastamaker_ci_statuses = pastamaker_ci_statuses
    p.pastamaker_weight = pastamaker_weight
    p.pastamaker_raw_data = pastamaker_raw_data

    # Missing Github API
    p.update_branch = webhack.web_github_update_branch
    p.update_branch_state = webhack.web_github_branch_status
