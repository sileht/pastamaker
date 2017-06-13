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
import json
import logging
import operator
import time

import github
import six.moves

from pastamaker import config
from pastamaker import utils
from pastamaker import webhack

LOG = logging.getLogger(__name__)


def pretty_pr(p):
    return "%s/%s#%s@%s (%s)" % (
        p.base.user.login, p.base.repo.name,
        p.number, p.base.ref, p.mergeable_state)


def is_branch_protected_as_expected(repo, branch):
    # NOTE(sileht): Can't get which permission I need to do this
    return True

    headers, data = repo._requester.requestJsonAndCheck(
        "GET",
        repo.url + "/branches/" + branch + "/protection",
        headers={'Accept': 'application/vnd.github.loki-preview+json'}
    )

    del data["url"]
    del data["required_pull_request_reviews"]["url"]
    del data["required_status_checks"]["url"]
    del data["required_status_checks"]["contexts_url"]
    del data["enforce_admins"]["url"]

    expected = {
        'required_pull_request_reviews': {'dismiss_stale_reviews': True},
        'required_status_checks': {'strict': True, 'contexts':
                                   ['continuous-integration/travis-ci']},
        'enforce_admins': {'enabled': True},
    }
    return data == expected


class PendingPulls(dict):
    def __init__(self, repo):
        super(PendingPulls, self).__init__()
        self._r = repo
        self._ident = ("pastamaker:%s:%s:" % (repo.owner.login, repo.name))

        self._conn = utils.get_redis()

        for k in self._conn.keys(self._ident + "*"):
            serialized = self._conn.get(k)
            headers, data = json.loads(serialized)
            p = github.PullRequest.PullRequest(self._r._requester,
                                               headers, data,
                                               completed=True)
            self[p.base.ref] = p

    def log(self):
        for branch, p in self.items():
            LOG.info("%s expected, sha %s", pretty_pr(p), p.head.sha)

    def add(self, p):
        serialized = json.dumps((p.raw_headers, p.raw_data))
        self._conn.set(self._ident + p.base.ref, serialized)
        self[p.base.ref] = p

    def clear(self, branch):
        self._conn.delete(self._ident + branch)


class PastaMakerEngine(object):
    def __init__(self, g, user, repo):
        self._g = g
        self._u = user
        self._r = repo

        self._allowed_reviewer_ids = map(lambda u: u.id,
                                         self._r.get_collaborators())

        self.pending_pulls = PendingPulls(self._r)

    def _pullrequest_refresh(self, p):
        # FIXME(sileht): use tenacity
        def is_valid(p):
            return p.mergeable_state not in ["unknown", None]

        if is_valid(p):
            return p

        # Github is currently processing this PR, we wait the completion
        while True:
            LOG.info("%s, refreshing...", pretty_pr(p))
            p = self._r.get_pull(p.number)
            if is_valid(p):
                break
            time.sleep(0.42)  # you known, this one always work

        LOG.info("%s, refreshed", pretty_pr(p))
        return p

    def _pullrequest_from_event_data(self, data):
        # TODO(sileht): do it only once in handle()
        # NOTE(sileht): Convert event payload, into pygithub object
        # instead of querying the API
        return github.PullRequest.PullRequest(self._r._requester, {},
                                              data["pull_request"],
                                              completed=True)

    def is_approved(self, p):

        def get_users(users, r):
            if r.user.id not in self._allowed_reviewer_ids:
                return users

            if r.state == 'APPROVED':
                users.add(r.user.login)
            elif r.user.login in users:
                users.remove(r.user.login)
            return users

        # Reviews are in chronological order
        users = functools.reduce(get_users, p.get_reviews(), set())
        return len(users) >= config.REQUIRED_APPROVALS

    ####################
    # Logic start here #
    ####################

    def handle(self, event_type, data):
        # Everything start here

        self.log_formated_event(event_type, data)
        self.pending_pulls.log()

        if event_type == "refresh":
            self.handle_refresh(data)

        elif event_type == "status":
            self.handle_status(data)

        # Someone closed the pending pull request without merging
        elif event_type == "pull_request":
            self.handle_pull_request(data)

        elif event_type == "pull_request_review":
            self.handle_pull_request_review(data)

    def handle_refresh(self, data):
        p = self.pending_pulls.get(data["branch"])
        if p:
            self.pull_request_proceed_or_find_next(p)
        else:
            self.find_next_pull_request_to_merge(data["branch"])

    def handle_status(self, data):
        # NOTE(sileht): We care only about success or failure state
        if data["state"] == "pending":
            return

        for branch, p in self.pending_pulls.items():
            if data["sha"] == p.head.sha:
                self.pull_request_proceed_or_find_next(p)
                return

    def handle_pull_request(self, data):
        p = self._pullrequest_from_event_data(data)

        pending_pull = self.pending_pulls.get(p.base.ref)
        if not pending_pull:
            # NOTE(sileht): If we are not waiting for any pull request
            # we don't care
            return

        if p.number == pending_pull.number:
            if data["action"] == "synchronize":
                # Base branch have been merged into the PR
                p = self._pullrequest_refresh(p)
                self.pending_pull.set(p)
                # Next step is status event

            elif data["action"] == "closed":
                # We just want to check if someone close the PR without
                # merging it
                self.find_next_pull_request_to_merge(pending_pull.base.ref)

    def handle_pull_request_review(self, data):
        p = self._pullrequest_from_event_data(data)

        pending_pull = self.pending_pulls.get(p.base.ref)
        if pending_pull:
            # Our ready PR have been changed, check if
            # we can still merge it or to pick another one
            if p.number == pending_pull.number:
                self.pull_request_proceed_or_find_next(p)

        elif (data["action"] == "submitted"
              and data["review"]["state"] == "approved"
              and self.is_approved(p)):
            # A PR got approvals, let's see if we can merge it
            self.pull_request_proceed_or_find_next(p)

    ###########################
    # Start machine goes here #
    ###########################

    def pull_request_proceed_or_find_next(self, p):
        """Do the next action for this pull request

        'p' is the top priority pull request to merge
        """
        LOG.info("%s, processing...", pretty_pr(p))

        p = self._pullrequest_refresh(p)
        self.pending_pulls.add(p)

        if self._is_approved(p):
            # Everything looks good
            if p.mergeable_state == "clean":
                if self._safe_merge(p):
                    LOG.info("%s merged", pretty_pr(p))
                    return

            # Have CI ok, at least 1 approval, but branch need to be updated
            elif p.mergeable_state == "behind":
                if self._get_ci_status(p) == "success":
                    # rebase it and wait the next pull_request event
                    # (synchronize)
                    if webhack.web_github_update_branch(p):
                        LOG.info("%s branch updated", pretty_pr(p))
                        return

            elif p.mergeable_state == "blocked":
                # We need to check why it's blocked
                if self.get_ci_status(p) == "pending":
                    # Let's wait the next status event
                    LOG.info("%s wating for CI completion", pretty_pr(p))
                    return
                # For other reason, we need to select another PR

            elif p.mergeable_state in ["unstable", "dirty", "ok"]:
                LOG.info("%s, unmergable", pretty_pr(p))

            else:
                LOG.warning("%s, FIXME unhandled mergeable_state",
                            pretty_pr(p))

        self.find_next_pull_request_to_merge(p.base.ref)

    def get_ci_status(self, p):
        head = self._r.get_commit(p.head.sha)
        return head.get_combined_status().state

    def dump_pulls_state(self, pulls):
        for p in pulls:
            LOG.info("%s, %s, %s, base-sha: %s, head-sha: %s)",
                     pretty_pr(p), self.get_ci_status(p),
                     p.created_at, p.base.sha, p.head.sha)

    @staticmethod
    def prioritize(p):
        # NOTE(sileht): this method is full of assumption
        # due to cleanup done in remove_unusable_pull_requests

        if not hasattr(p, "pastamaker_priority"):
            if p.mergeable_state == "clean":
                value = 10
            elif p.mergeable_state == "blocked":
                # CI is pending here but PR is up2date and approvals ok
                # It will be clean very soon
                value = 7
            elif p.mergeable_state == "behind":
                # CI is success here, other have been dropped before
                value = 5
            else:
                value = 0
            setattr(p, "pastamaker_priority", value)
        return p

    def remove_unusable_pull_requests(self, p):
        if not self.is_approved(p):
            return False

        elif p.mergeable_state == "clean":
            # Best PR ever
            return True

        elif p.mergeable_state == "blocked":
            if self.get_ci_status(p) == "pending":
                # Maybe clean soon, so keep it if we can rebase
                branch_status = webhack.web_github_branch_status(p)
                return branch_status == "clean"

        elif p.mergeable_state == "behind":
            if self.get_ci_status(p) == "success":
                # Not up2date, but ready to merge,
                # we ensure "Update branch" exists
                branch_status = webhack.web_github_branch_status(p)
                return branch_status not in ["unknown", "dirty"]

        return False

    def find_next_pull_request_to_merge(self, branch):
        log_prefix = (self._u.login + "/" + self._r.name +
                      "#??@" + branch + " (??)")
        LOG.info("%s, looking for pull requests mergeable", log_prefix)

        self.pending_pulls.clear(branch)

        pulls = self._r.get_pulls(sort="created", direction="asc", base=branch)
        # Ensure we don't have unknown state
        pulls = six.moves.map(self._pullrequest_refresh, pulls)
        # Remove unusable PR
        pulls = filter(self.remove_unusable_pull_requests, pulls)
        # Calculate priorities
        pulls = six.moves.map(self.prioritize, pulls)
        sort_key = operator.attrgetter('pastamaker_priority', 'created_at')
        pulls = list(sorted(pulls, key=sort_key, reverse=True))
        if pulls:
            self.dump_pulls_state(pulls)
            self.pull_request_proceed_or_find_next(pulls[0])
        LOG.info("%s, %s pull request(s) mergeable" % (log_prefix, len(pulls)))

    def log_formated_event(self, event_type, data):
        p_info = "%s/%s#??@%s (??)" % (data["repository"]["owner"]["login"],
                                       data["repository"]["name"], "%s")

        if event_type == "pull_request":
            p_info = pretty_pr(self._pullrequest_from_event_data(data))
            extra = "action: %s" % data["action"]

        elif event_type == "pull_request_review":
            p_info = pretty_pr(self._pullrequest_from_event_data(data))
            extra = "action: %s, review-state: %s" % (data["action"],
                                                      data["review"]["state"])

        elif event_type == "status":
            p_info = p_info % "?????"
            extra = "ci-status: %s, sha: %s" % (data["state"], data["sha"])

        elif event_type == "refresh":
            p_info = p_info % data["branch"]
            extra = ""
        else:
            p_info = p_info % "?????"
            extra = " ignored"

        LOG.info("%s - got event '%s' - %s", p_info, event_type, extra)

    @staticmethod
    def safe_merge(p, **post_parameters):

        post_parameters["sha"] = p.head.sha
        # FIXME(sileht): use p.merge when it will
        # support sha and merge_method arguments
        try:
            post_parameters['merge_method'] = "rebase"
            headers, data = p._requester.requestJsonAndCheck(
                "PUT", p.url + "/merge", input=post_parameters)
            return github.PullRequestMergeStatus.PullRequestMergeStatus(
                p._requester, headers, data, completed=True)
        except github.GithubException as e:
            if e.data["message"] != "This branch can't be rebased":
                LOG.exception("%s merge fail: %d, %s",
                              pretty_pr(p), e.status, e.data["message"])
                return

            # If rebase fail retry with merge
            post_parameters['merge_method'] = "merge"
            try:
                headers, data = p._requester.requestJsonAndCheck(
                    "PUT", p.url + "/merge", input=post_parameters)
                return github.PullRequestMergeStatus.PullRequestMergeStatus(
                    p._requester, headers, data, completed=True)
            except github.GithubException as e:
                LOG.exception("%s merge fail: %d, %s",
                              pretty_pr(p), e.status, e.data["message"])

            # FIXME(sileht): depending on the kind of failure we can endloop
            # to try to merge the pr again and again.
            # to repoduce the issue
