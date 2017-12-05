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


from concurrent import futures
import github
import lz4.block
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
                "/pull/XXX@" + branch + " (-)")

    def log_formated_event(self, event_type, incoming_pull, data):
        if event_type == "pull_request":
            p_info = incoming_pull.pretty()
            extra = ", action: %s" % data["action"]

        elif event_type == "pull_request_review":
            p_info = incoming_pull.pretty()
            extra = ", action: %s, review-state: %s" % (
                data["action"], data["review"]["state"])

        elif event_type == "status":
            if incoming_pull:
                p_info = incoming_pull.pretty()
            else:
                p_info = self._get_logprefix()
            extra = ", ci-status: %s, sha: %s" % (data["state"], data["sha"])

        elif event_type == "refresh":
            if incoming_pull:
                p_info = incoming_pull.pretty()
            else:
                p_info = self._get_logprefix(data["refresh_ref"])
            extra = ""
        else:
            if incoming_pull:
                p_info = incoming_pull.pretty()
            else:
                p_info = self._get_logprefix()
            extra = ", ignored"

        LOG.info("***********************************************************")
        LOG.info("%s received event '%s'%s", p_info, event_type, extra)

    def handle(self, event_type, data):
        # Everything start here

        if event_type == "status":
            # Don't compute the queue for nothing
            if data["context"].startswith("pastamaker/"):
                return
            elif data["context"] == "continuous-integration/travis-ci/push":
                return

        # Get the current pull request
        incoming_pull = gh_pr.from_event(self._r, data)
        if not incoming_pull:
            if event_type == "status":
                issues = list(self._g.search_issues("is:pr %s" % data["sha"]))
                if len(issues) >= 1:
                    incoming_pull = self._r.get_pull(issues[0].number)

            elif (event_type == "refresh" and
                  data["refresh_ref"].startswith("pull/")):
                incoming_pull = self._r.get_pull(int(data["refresh_ref"][5:]))

        # Gather missing github/travis information and compute weight
        if incoming_pull:
            incoming_pull = incoming_pull.fullify()

        # Get the current branch
        current_branch = None
        if incoming_pull:
            current_branch = incoming_pull.base.ref
        elif (event_type == "refresh" and
              data["refresh_ref"].startswith("branch/")):
            current_branch = data["refresh_ref"][7:]
        else:
            LOG.info("No pull request or branch found in the event, ignoring")
            return

        # Log the event
        self.log_formated_event(event_type, incoming_pull, data)

        # Unhandled and already logged
        if event_type not in ["pull_request", "pull_request_review",
                              "status", "refresh"]:
            LOG.info("No need to proceed queue")
            return

        # NOTE(sileht): refresh only travis detail
        if event_type == "status" and data["state"] == "pending":
            self.get_updated_queues_from_cache(current_branch,
                                               incoming_pull)
            LOG.info("No need to proceed queue")
            return

        # NOTE(sileht): We check the state of incoming_pull and the event
        # because user can have restart a travis job between the event
        # received and when we looks at it with travis API
        ending_states = ["failure", "error", "success"]
        if (event_type == "status"
                and data["state"] in ending_states
                and data["context"] in ["continuous-integration/travis-ci",
                                        "continuous-integration/travis-ci/pr"]
                and incoming_pull.pastamaker["travis_state"] in ending_states
                and incoming_pull.pastamaker["travis_detail"]):
            incoming_pull.pastamaker_travis_post_build_results()

        # NOTE(sileht): PullRequest updated or comment posted, maybe we need to
        # update github
        need_status_update = ((event_type == "pull_request"
                               and data["action"] in ["opened", "synchronize"])
                              or event_type == "pull_request_review")
        if need_status_update and incoming_pull:
            if not incoming_pull.pastamaker_github_post_check_status():
                # Status not updated, don't need to update the queue
                LOG.info("No need to proceed queue")
                return

        # Get and refresh the queues
        if not incoming_pull:
            queues = self.get_updated_queues_from_github(current_branch)
            if event_type == "refresh":
                for p in queues:
                    p.pastamaker_github_post_check_status()
            else:
                LOG.warning("FIXME: We got a event without incoming_pull:"
                            "%s : %s" % (event_type, data))
        else:
            if event_type == "refresh":
                incoming_pull.pastamaker_github_post_check_status()
            queues = self.get_updated_queues_from_cache(current_branch,
                                                        incoming_pull)

        # Proceed the queue
        if queues:
            # protect the branch before doing anything
            try:
                gh_branch.protect_if_needed(self._r, current_branch)
            except github.UnknownObjectException:
                LOG.exception("Fail to protect branch, disabled automerge")
                return
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
        LOG.info("%s selected", p.pretty())

        if p.pastamaker["weight"] >= 11:
            if p.pastamaker_merge():
                # Wait for the closed event now
                LOG.info("%s -> merged", p.pretty())
            else:
                LOG.info("%s -> merge fail", p.pretty())

        elif p.mergeable_state == "behind":
            commit = self._r.get_commit(p.head.sha)
            status = commit.get_combined_status()
            if status.state == "success":
                # rebase it and wait the next pull_request event
                # (synchronize)
                if p.pastamaker_update_branch():
                    LOG.info("%s -> branch updated", p.pretty())
                else:
                    LOG.info("%s -> branch not updatable, "
                             "manual intervention required", p.pretty())
            else:
                LOG.info("%s -> github combined status != success", p.pretty())

        else:
            LOG.info("%s -> weight < 10", p.pretty())

    def set_cache_queues(self, branch, raw_pulls):
        key = "queues~%s~%s~%s" % (self._u.login, self._r.name, branch)
        if raw_pulls:
            payload = ujson.dumps(raw_pulls)
            payload = lz4.block.compress(payload)
            self._redis.set(key, payload)
        else:
            self._redis.delete(key)
        self._redis.publish("update", key)

    def get_updated_queues_from_cache(self, branch, incoming_pull):
        key = "queues~%s~%s~%s" % (self._u.login, self._r.name, branch)
        data = self._redis.get(key)
        if data:
            pulls = ujson.loads(lz4.block.decompress(data))
        else:
            pulls = []
        found = False
        for i, pull in list(enumerate(pulls)):
            pull = gh_pr.from_cache(self._r, pull)
            if pull.number == incoming_pull.number:
                LOG.info("%s: replaced in cache" % incoming_pull.pretty())
                pull = incoming_pull
                found = True
            pulls[i] = pull
        if incoming_pull.is_merged():
            if incoming_pull in pulls:
                LOG.info("%s: removed from cache" % incoming_pull.pretty())
                pulls.remove(incoming_pull)
        elif not found:
            LOG.info("%s: appended to cache" % incoming_pull.pretty())
            pulls.append(incoming_pull)
        return self.sort_save_and_log_queues(branch, pulls)

    def get_updated_queues_from_github(self, branch):
        LOG.info("%s, retrieving pull requests", self._get_logprefix(branch))
        pulls = self._r.get_pulls(sort="created", direction="asc", base=branch)
        LOG.info("%s, fullify pull requests", self._get_logprefix(branch))
        with futures.ThreadPoolExecutor(max_worker=1) as tpe:
            list(tpe.map(lambda p: p.fullify(), pulls))
        return self.sort_save_and_log_queues(branch, pulls)

    def sort_save_and_log_queues(self, branch, pulls):
        sort_key = operator.attrgetter('pastamaker_weight', 'updated_at')
        pulls = list(sorted(pulls, key=sort_key, reverse=True))
        for p in pulls:
            LOG.info("%s, sha: %s->%s)", p.pretty(), p.base.sha, p.head.sha)
        LOG.info("%s, %s pull request(s) found" % (self._get_logprefix(branch),
                                                   len(pulls)))
        raw_queues = [p.jsonify() for p in pulls]
        self.set_cache_queues(branch, raw_queues)
        return pulls
