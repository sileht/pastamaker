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

import json
import logging
import operator

import github
import six.moves

from pastamaker import pr
from pastamaker import utils

LOG = logging.getLogger(__name__)


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
            LOG.info("%s expected, sha %s", p.pretty(), p.head.sha)

    def add(self, p):
        p.pastamaker_update(force=True)
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
        self.pending_pulls = PendingPulls(self._r)

    def _get_logprefix(self, branch="<unknown>"):
        return (self._u.login + "/" + self._r.name +
                "/pull/?@" + branch + " (?, ?)")

    def log_formated_event(self, event_type, incoming_pull, data):
        if event_type == "pull_request":
            p_info = incoming_pull.pretty()
            extra = "action: %s" % data["action"]

        elif event_type == "pull_request_review":
            p_info = incoming_pull.pretty()
            extra = "action: %s, review-state: %s" % (data["action"],
                                                      data["review"]["state"])

        elif event_type == "status":
            p_info = self._get_logprefix()
            extra = "ci-status: %s, sha: %s" % (data["state"], data["sha"])

        elif event_type == "refresh":
            p_info = self._get_logprefix(data["branch"])
            extra = ""
        else:
            if incoming_pull:
                p_info = incoming_pull.pretty()
            else:
                p_info = self._get_logprefix()
            extra = " ignored"

        LOG.info("%s - got event '%s' - %s", p_info, event_type, extra)

    def handle(self, event_type, data):
        # Everything start here

        incoming_pull = pr.from_event(self._r, data)

        self.log_formated_event(event_type, incoming_pull, data)
        self.pending_pulls.log()

        handler = getattr(self, "handle_%s" % event_type)
        if handler:
            handler(incoming_pull, data)

    def handle_refresh(self, incoming_pull, data):
        pending_pull = self.pending_pulls.get(data["branch"])
        if pending_pull:
            self.proceed_pull_or_find_next(pending_pull)
        else:
            self.find_next_pull_to_merge(data["branch"])

    def handle_status(self, incoming_pull, data):
        # NOTE(sileht): We care only about success or failure state
        if data["state"] == "pending":
            return

        for branch, p in self.pending_pulls.items():
            if data["sha"] == p.head.sha:
                self.proceed_pull_or_find_next(p)
                return

    def handle_pull_request(self, incoming_pull, data):
        pending_pull = self.pending_pulls.get(incoming_pull.base.ref)
        if not pending_pull:
            # NOTE(sileht): If we are not waiting for any pull request
            # we don't care
            return

        if incoming_pull.number == pending_pull.number:
            if data["action"] == "synchronize":
                # Base branch have been merged into the PR
                self.pending_pulls.add(incoming_pull)
                # Next step is status event

            elif data["action"] == "closed":
                # We just want to check if someone close the PR without
                # merging it
                self.find_next_pull_to_merge(incoming_pull.base.ref)

    def handle_pull_request_review(self, incoming_pull, data):

        pending_pull = self.pending_pulls.get(incoming_pull.base.ref)
        if pending_pull:
            # Our ready PR have been changed, check if
            # we can still merge it or to pick another one
            if incoming_pull.number == pending_pull.number:
                self.proceed_pull_or_find_next(incoming_pull)

        elif (data["action"] == "submitted"
              and data["review"]["state"] == "approved"
              and incoming_pull.approved):
            # A PR got approvals, let's see if we can merge it
            self.proceed_pull_or_find_next(incoming_pull)

    ###########################
    # Start machine goes here #
    ###########################

    def proceed_pull_or_find_next(self, p):
        """Do the next action for this pull request

        'p' is the top priority pull request to merge
        """
        LOG.info("%s, processing...", p.pretty())

        # NOTE(sileht): This also refresh the PR, following code expects the
        # mergeable_state is up2date
        self.pending_pulls.add(p)

        if p.approved:
            # Everything looks good
            if p.mergeable_state == "clean":
                if p.pastamaker_merge():
                    LOG.info("%s merged", p.pretty())

            # Have CI ok, at least 1 approval, but branch need to be updated
            elif p.mergeable_state == "behind":
                if p.ci_status == "success":
                    # rebase it and wait the next pull_request event
                    # (synchronize)
                    if p.update_branch():
                        LOG.info("%s branch updated", p.pretty())
                        return

            elif p.mergeable_state == "blocked":
                # We need to check why it's blocked
                if p.ci_status == "pending":
                    # Let's wait the next status event
                    LOG.info("%s wating for CI completion", p.pretty())
                    return
                # For other reason, we need to select another PR

            elif p.mergeable_state in ["unstable", "dirty", "ok"]:
                LOG.info("%s, unmergable", p.pretty())

            else:
                LOG.warning("%s, FIXME unhandled mergeable_state",
                            p.pretty())

        self.find_next_pull_to_merge(p.base.ref)

    def dump_pulls_state(self, pulls):
        for p in pulls:
            LOG.info("%s, %s, %s, base-sha: %s, head-sha: %s)",
                     p.pretty(), p.ci_status,
                     p.created_at, p.base.sha, p.head.sha)

    def find_next_pull_to_merge(self, branch):
        LOG.info("%s, looking for pull requests mergeable",
                 self._get_logprefix(branch))

        self.pending_pulls.clear(branch)

        sort_key = operator.attrgetter('pastamaker_priority', 'created_at')

        pulls = self._r.get_pulls(sort="created", direction="asc", base=branch)
        pulls = six.moves.map(lambda p: p.pastamaker_update(), pulls)
        pulls = list(filter(lambda p: p.pastamaker_priority >= 0,
                            sorted(pulls, key=sort_key, reverse=True)))
        if pulls:
            self.dump_pulls_state(pulls)
            self.proceed_pull_or_find_next(pulls[0])
        LOG.info("%s, %s pull request(s) mergeable" %
                 (self._get_logprefix(branch), len(pulls)))
