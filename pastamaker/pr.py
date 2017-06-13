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

import functools
import logging
import time

import github

from pastamaker import config
from pastamaker import webhack

LOG = logging.getLogger(__name__)


def pretty(self):
    return "%s/%s#%s@%s (%s)" % (
        self.base.user.login, self.base.repo.name,
        self.number, self.base.ref, self.mergeable_state)


def mergeable_state_is_valid(self):
    return self.mergeable_state not in ["unknown", None]


def refresh(self):
    # FIXME(sileht): use tenacity
    if self.mergeable_state_is_valid():
        return self

    # Github is currently processing this PR, we wait the completion
    while True:
        LOG.info("%s, refreshing...", self.pretty())
        self.update()
        if self.mergeable_state_is_valid():
            break
        time.sleep(0.42)  # you known, this one always work

    if hasattr(self, "_pastamaker_priority"):
        delattr(self, "_pastamaker_priority")
    LOG.info("%s, refreshed", self.pretty())
    return self


def approved(self):
    allowed = [u.id for u in self.base.repo.get_collaborators()]

    def get_users(users, review):
        if review.user.id not in allowed:
            return users

        if review.state == 'APPROVED':
            users.add(review.user.login)
        elif review.user.login in users:
            users.remove(review.user.login)
        return users

    # Reviews are in chronological order
    users = functools.reduce(get_users, self.get_reviews(), set())
    return len(users) >= config.REQUIRED_APPROVALS


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


def ci_status(self):
    # Only work for PR with less than 250 commites
    return list(self.get_commits())[-1].get_combined_status().state


def pastamaker_priority(self):
    if not hasattr(self, "_pastamaker_priority"):
        if not self.approved():
            priority = -1
        elif self.mergeable_state == "clean":
            # Best PR ever
            priority = 10
        elif (self.mergeable_state == "blocked"
              and self.ci_status == "pending"
              and self.update_branch_state == "clean"):
            # Maybe clean soon, so keep it if we can rebase
            priority = 7
        elif (self.mergeable_state == "behind"
              and self.ci_status == "success"
              and self.update_branch_state not in ["unknown", "dirty"]):
            # Not up2date, but ready to merge, is branch updatable
            priority = 5
        else:
            priority = -1
        setattr(self, "_pastamaker_priority", priority)
    return self._pastamaker_priority


def from_event(repo, data):
    # TODO(sileht): do it only once in handle()
    # NOTE(sileht): Convert event payload, into pygithub object
    # instead of querying the API
    return github.PullRequest.PullRequest(repo._requester, {},
                                          data["pull_request"],
                                          completed=True)


def monkeypatch_github():
    p = github.PullRequest.PullRequest
    p.pretty = pretty
    p.mergeable_state_is_valid = mergeable_state_is_valid
    p.refresh = refresh
    p.approved = approved
    p.ci_status = property(ci_status)
    p.pastamaker_merge = pastamaker_merge
    p.pastamaker_priority = property(pastamaker_priority)

    # Missing Github API
    p.update_branch = webhack.web_github_update_branch
    p.update_branch_state = property(webhack.web_github_branch_status)
