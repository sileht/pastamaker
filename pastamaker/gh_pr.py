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

import github

from pastamaker import config
from pastamaker import gh_pr_fullifier
from pastamaker import gh_update_branch

LOG = logging.getLogger(__name__)


def pretty(self):
    extra = getattr(self, "pastamaker", {})
    status = extra.get("combined_status", "nc")
    approvals = len(extra["approvals"][0]) if "approvals" in extra else "nc"
    weight = extra["weight"] if extra.get("weight", -1) >= 0 else "NA"
    synced = extra.get("sync_with_master", "nc")
    return "%s/%s/pull/%s@%s (%s/%s/%s/%s/%s)" % (
        self.base.user.login,
        self.base.repo.name,
        self.number,
        self.base.ref,
        ("merged" if self.state == "merged"
         else (self.mergeable_state or "none")),
        synced,
        status,
        approvals,
        weight
    )


def pastamaker_github_post_check_status(self, installation_id, updater_token,
                                        branch_policy_error):

    if branch_policy_error:
        state = "failure"
        link = "and"
        description = "PR automerge disabled (%s)", branch_policy_error
        # FIXME(sileht): put url to mergify doc
        target_url = config.BASE_URL
    else:
        state = "success"
        link = "but"
        description = "PR automerge enabled"
        target_url = config.BASE_URL

    if not self.maintainer_can_modify:
        state = "failure"
        description += ", %s PR owner doesn't allow modification" % link
    elif not updater_token:
        state = "failure"
        description += ", %s no user access_token setuped for rebasing" % link
        target_url += "/login?installation_id=%s" % installation_id

    detail = []
    if self.pastamaker["combined_status"] != "success":
        detail.append("CI")
    if not self.pastamaker["approved"]:
        detail.append("approvals")

    if detail:
        description += ", warting for %s" % " and ".join(detail)

    context = "%s/pr" % config.CONTEXT
    old_context = "%s/reviewers" % config.CONTEXT
    context_to_update = None

    commit = self.base.repo.get_commit(self.head.sha)
    for s in commit.get_statuses():
        if s.context in [context, old_context]:
            if (s.state != state or s.description != description):
                context_to_update = s.context
            break
    else:
        context_to_update = context

    if context_to_update:
        # NOTE(sileht): We can't use commit.create_status() because
        # if use the head repo instead of the base repo
        try:
            self._requester.requestJsonAndCheck(
                "POST",
                self.base.repo.url + "/statuses/" + self.head.sha,
                input={'state': state,
                       'description': description,
                       'target_url': target_url,
                       'context': context_to_update},
                headers={'Accept':
                         'application/vnd.github.machine-man-preview+json'}
            )
        except github.GithubException as e:
            LOG.exception("%s set status fail: %s",
                          self.pretty(), e.data["message"])

    return context_to_update is not None


def pastamaker_travis_post_build_results(self):
    message = ["Tests %s for HEAD %s\n" % (
        self.pastamaker["travis_state"].upper(),
        self.head.sha)]
    for i, job in enumerate(self.pastamaker["travis_detail"]["jobs"]):
        try:
            state = job["state"].upper()
            if state == "PASSED":
                icon = u" ✅"
            elif state == "FAILED":
                icon = u" ❌"
            else:
                icon = u""
            message.append(u'- [%s](%s): %s%s' % (
                job["config"].get("env", "JOB #%d" % i),
                job["log_url"],
                state, icon,
            ))
        except KeyError:
            LOG.error("%s, malformed travis job: %s",
                      self.pretty(), job)
    message = "\n".join(message)
    LOG.debug("%s POST comment: %s" % (self.pretty(), message))
    self.create_issue_comment(message)


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


def from_cache(repo, data):
    # NOTE(sileht): Reload our PullRequest custom object from cache data
    # instead of querying the API
    p = github.PullRequest.PullRequest(
        repo._requester, {}, data, completed=True)
    return p.fullify(data)


def monkeypatch_github():
    p = github.PullRequest.PullRequest

    # Missing attribute
    p.maintainer_can_modify = property(
        lambda p: p.raw_data["maintainer_can_modify"])

    p.pretty = pretty
    p.fullify = gh_pr_fullifier.fullify
    p.jsonify = gh_pr_fullifier.jsonify

    p.pastamaker_merge = pastamaker_merge
    p.pastamaker_github_post_check_status = pastamaker_github_post_check_status
    p.pastamaker_travis_post_build_results = \
        pastamaker_travis_post_build_results

    # Missing Github API
    p.pastamaker_update_branch = gh_update_branch.update_branch

    # FIXME(sileht): remove me, used by engine for sorting pulls
    p.pastamaker_weight = property(lambda p: p.pastamaker["weight"])

    # FIXME(sileht): Workaround https://github.com/PyGithub/PyGithub/issues/660
    github.PullRequestReview.PullRequestReview._completeIfNeeded = (
        lambda self: None)
