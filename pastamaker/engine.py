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
import operator

import six.moves
import ujson

from pastamaker import gh_branch  # noqa
from pastamaker import gh_pr
from pastamaker import utils

LOG = logging.getLogger(__name__)


class PastaMakerEngine(object):
    def __init__(self, g, user, repo):
        self._g = g
        self._u = user
        self._r = repo
        self._redis = utils.get_redis()

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
            if incoming_pull:
                p_info = incoming_pull.pretty()
            else:
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

        incoming_pull = gh_pr.from_event(self._r, data)
        if not incoming_pull and event_type == "status":
            issues = list(self._g.search_issues("is:pr %s" % data["sha"]))
            if len(issues) >= 1:
                incoming_pull = self._r.get_pull(issues[0].number)

        self.log_formated_event(event_type, incoming_pull, data)

        current_branch = None
        if incoming_pull:
            current_branch = incoming_pull.base.ref
        elif event_type == "refresh":
            current_branch = data["branch"]
        else:
            LOG.info("No pull request found in the event, ignoring")
            return

        # FIXME(sileht): Need to figure out what permissions we need to do this
        # gh_branch.protect_if_needed(self._r, current_branch)

        need_status_update = ((event_type == "pull_request"
                               and data["action"] == "opened")
                              or event_type == "pull_request_review")
        if need_status_update:
            if not incoming_pull.pastamaker_update_status():
                # Status not updated, don't need to update the queue
                return

        if event_type == "status":
            # Don't compute the queue for nothing
            if data["context"].startswith("pastamaker/"):
                return
            elif data["state"] == "pending":
                return

        # NOTE(sileht): We currently rebuild the queue on each event to
        # refresh the UI correctly. We obviously can be smarter, but we prefer
        # keeping it very simple for now
        queues = self.get_pull_requests_queue(current_branch)

        if event_type == "refresh":
            for pr in queues:
                pr.pastamaker_update_status()

        self.set_cache_queues(current_branch, queues)
        if queues:
            self.proceed_queues(queues)
        else:
            LOG.info("Nothing queued, skipping the event")

    ###########################
    # State machine goes here #
    ###########################

    def proceed_queues(self, queues):
        """Do the next action for this pull request

        'p' is the top priority pull request to merge
        """

        p = queues[0]

        # NOTE(sileht): This also refresh the PR, following code expects the
        # mergeable_state is up2date

        if p.approved:
            LOG.info("%s, processing...", p.pretty())

            if p.ci_status == "pending":
                LOG.info("%s waiting for CI completion", p.pretty())
                return

            # Everything looks good
            elif p.mergeable_state == "clean":
                if p.pastamaker_merge():
                    LOG.info("%s merged", p.pretty())
                    # Wait for the closed event
                    return

            # Have CI ok, at least 1 approval, but branch need to be updated
            elif p.mergeable_state == "behind":
                if p.ci_status == "success":
                    # rebase it and wait the next pull_request event
                    # (synchronize)
                    if p.update_branch():
                        LOG.info("%s branch updated", p.pretty())
                        return

            elif p.mergeable_state in ["unstable", "dirty", "ok"]:
                LOG.info("%s, unmergable", p.pretty())

            else:
                LOG.warning("%s, FIXME unhandled mergeable_state",
                            p.pretty())

    def set_cache_queues(self, branch, pulls):
        key = "queues~%s~%s~%s" % (self._u.login, self._r.name, branch)
        if pulls:
            self._redis.set(key, ujson.dumps(
                [p.pastamaker_raw_data for p in pulls]))
        else:
            self._redis.delete(key)
        self._redis.publish("update", key)

    def dump_pulls_state(self, branch, pulls):
        for p in pulls:
            LOG.info("%s, %s, %s, base-sha: %s, head-sha: %s)",
                     p.pretty(), p.ci_status,
                     p.created_at, p.base.sha, p.head.sha)

    def get_pull_requests_queue(self, branch):
        LOG.info("%s, looking for pull requests mergeable",
                 self._get_logprefix(branch))

        sort_key = operator.attrgetter('pastamaker_weight', 'updated_at')

        pulls = self._r.get_pulls(sort="created", direction="asc", base=branch)
        pulls = six.moves.map(lambda p: p.pastamaker_update(), pulls)
        pulls = list(sorted(pulls, key=sort_key, reverse=True))
        self.dump_pulls_state(branch, pulls)
        LOG.info("%s, %s pull request(s)" %
                 (self._get_logprefix(branch), len(pulls)))
        return pulls
