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
import rq
import rq.worker
import six.moves

from pastamaker import config
from pastamaker import utils
from pastamaker import webhack

LOG = logging.getLogger(__name__)


def pretty_ident(ident):
    _, user, repo, branch = ident.split(":")
    return user + "/" + repo + "#??@" + branch + " (??)"


def pretty_pr(p):
    return "%s/%s#%s@%s (%s)" % (
        p.base.user.login, p.base.repo.name,
        p.number, p.base.ref, p.mergeable_state)


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


def is_approved(p):
    valid_user_ids = map(lambda u: u.id,
                         p.base.repo.organization.get_members())

    def get_users(users, r):
        if r.user.id not in valid_user_ids:
            return users

        if r.state == 'APPROVED':
            users.add(r.user.login)
        elif r.user.login in users:
            users.remove(r.user.login)
        return users

    # Reviews are in chronological order
    users = functools.reduce(get_users, p.get_reviews(), set())
    return len(users) >= config.REQUIRED_APPROVALS


def pending_pull_ident(user, repo):
    return ("pastamaker:%s:%s:" % (user, repo))


def pending_pull_set(ident, p):
    serialized = json.dumps((p.raw_headers, p.raw_data))
    conn = utils.get_redis()
    conn.set(ident + p.base.ref, serialized)


def pending_pulls_get(repo, ident):
    conn = utils.get_redis()
    pulls = {}
    for k in conn.keys(ident + "*"):
        serialized = conn.get(k)
        headers, data = json.loads(serialized)
        p = github.PullRequest.PullRequest(repo._requester,
                                           headers, data,
                                           completed=True)
        pulls[p.base.ref] = p
    return pulls


def pending_pull_clear(ident, branch):
    conn = utils.get_redis()
    conn.delete(ident + branch)


def is_up2date(repo, p, branch_sha=None):
    if p.mergeable_state == "behind":
        return False

    # FIXME(sileht): This cannot be always true, both sha
    # can be the same but PR not up2date
    if not branch_sha:
        branch_sha = repo.get_git_ref("heads/" + p.base.ref).object.sha
    return p.base.sha == branch_sha


def get_ci_status(repo, p):
    head = repo.get_commit(p.head.sha)
    return head.get_combined_status().state


def dump_pulls_state(repo, pulls):
    for p in pulls:
        LOG.info("%s, %s, %s, base-sha: %s, head-sha: %s)",
                 pretty_pr(p), get_ci_status(repo, p),
                 p.created_at, p.base.sha, p.head.sha)


def prioritize(repo, p):
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


def remove_unusable_pull_requests(repo, p):
    if not is_approved(p):
        return False

    elif p.mergeable_state == "clean":
        # Best PR ever
        return True

    elif p.mergeable_state == "blocked":
        if get_ci_status(repo, p) == "pending":
            # Maybe clean soon, so keep it if we can rebase
            branch_status = webhack.web_github_branch_status(p)
            return branch_status == "clean"

    elif p.mergeable_state == "behind":
        if get_ci_status(repo, p) == "success":
            # Not up2date, but ready to merge,
            # we ensure "Update branch" exists
            branch_status = webhack.web_github_branch_status(p)
            return branch_status not in ["unknown", "dirty"]

    return False


def find_next_pull_request_to_merge(repo, ident, branch):
    LOG.info("%s, looking for pull requests mergeable" %
             pretty_ident(ident + branch))
    pending_pull_clear(ident, branch)

    pulls = repo.get_pulls(sort="created", direction="asc", base=branch)
    # Ensure we don't have unknown state
    pulls = six.moves.map(functools.partial(refresh_pull_request, repo), pulls)
    # Remove unusable PR
    pulls = filter(functools.partial(remove_unusable_pull_requests, repo),
                   pulls)
    # Calculate priorities
    pulls = six.moves.map(functools.partial(prioritize, repo), pulls)
    sort_key = operator.attrgetter('pastamaker_priority', 'created_at')
    pulls = list(sorted(pulls, key=sort_key, reverse=True))
    if pulls:
        dump_pulls_state(repo, pulls)
        pull_request_proceed_or_find_next(repo, ident, pulls[0])
    LOG.info("%s, %s pull request(s) mergeable" %
             (pretty_ident(ident + branch), len(pulls)))


def refresh_pull_request(repo, p):
    # Github is currently processing this PR, we wait it finish
    while p.mergeable_state == "unknown" or p.mergeable_state is None:
        time.sleep(0.42)  # you known, this one always work
        LOG.info("%s, refreshing...", pretty_pr(p))
        p = repo.get_pull(p.number)
    LOG.info("%s, refreshed", pretty_pr(p))
    return p


def pull_request_proceed_or_find_next(repo, ident, p):
    """Do the next action for this pull request

    'p' is the top priority pull request to merge
    """
    LOG.info("%s, processing...", pretty_pr(p))

    p = refresh_pull_request(repo, p)
    pending_pull_set(ident, p)

    if is_approved(p):
        # Everything looks good
        if p.mergeable_state == "clean":
            if safe_merge(p):
                LOG.info("%s merged", pretty_pr(p))
                return

        # Have CI ok, at least 1 approval, but branch need to be updated
        elif p.mergeable_state == "behind":
            if get_ci_status(repo, p) == "success":
                # rebase it and wait the next pull_request event (synchronize)
                if webhack.web_github_update_branch(p):
                    LOG.info("%s branch updated", pretty_pr(p))
                    return

        elif p.mergeable_state == "blocked":
            # We need to check why it's blocked
            if get_ci_status(repo, p) == "pending":
                # Let's wait the next status event
                LOG.info("%s wating for CI completion", pretty_pr(p))
                return
            # For other reason, we need to select another PR

        elif p.mergeable_state in ["unstable", "dirty", "ok"]:
            LOG.info("%s, unmergable", pretty_pr(p))

        else:
            LOG.warning("%s, FIXME unhandled mergeable_state", pretty_pr(p))

    find_next_pull_request_to_merge(repo, ident, p.base.ref)


def handle_status(repo, ident, pending_pulls, data):
    # NOTE(sileht): We care only about success or failure state
    if data["state"] == "pending":
        return

    for branch, p in pending_pulls.items():
        if data["sha"] == p.head.sha:
            pull_request_proceed_or_find_next(repo, ident, p)
            return


def pr_from_event_data(repo, data):
    # NOTE(sileht): Convert event payload, into pygithub object
    # instead of querying the API
    return github.PullRequest.PullRequest(repo._requester, {},
                                          data, completed=True)


def handle_pull_request(repo, ident, pending_pulls, data):
    p = pr_from_event_data(repo, data["pull_request"])

    pending_pull = pending_pulls.get(p.base.ref)
    if not pending_pull:
        # NOTE(sileht): If we are not waiting for any pull request
        # we don't care
        return

    if p.number == pending_pull.number:
        if data["action"] == "synchronize":
            # Base branch have been merged into the PR
            p = refresh_pull_request(repo, p)
            pending_pull_set(ident, p)
            # Next step is status event

        elif data["action"] == "closed":
            # We just want to check if someone close the PR without merging it
            find_next_pull_request_to_merge(repo, ident, pending_pull.base.ref)


def handle_pull_request_review(repo, ident, pending_pulls, data):
    p = pr_from_event_data(repo, data["pull_request"])

    pending_pull = pending_pulls.get(p.base.ref)
    if pending_pull:
        # Our ready PR have been changed, check if
        # we can still merge it or to pick another one
        if p.number == pending_pull.number:
            pull_request_proceed_or_find_next(repo, ident, p)

    elif (data["action"] == "submitted"
          and data["review"]["state"] == "approved"
          and is_approved(p)):
        # A PR got approvals, let's see if we can merge it
        pull_request_proceed_or_find_next(repo, ident, p)


def handle_refresh(repo, ident, pending_pulls, data):
    p = pending_pulls.get(data["branch"])
    if p:
        pull_request_proceed_or_find_next(repo, ident, p)
    else:
        find_next_pull_request_to_merge(repo, ident, data["branch"])


def log_formated_event(repo, event_type, data):
    p_info = "%s/%s#??@%s (??)" % (data["repository"]["owner"]["login"],
                                   data["repository"]["name"], "%s")

    if event_type == "pull_request":
        p_info = pretty_pr(pr_from_event_data(repo, data["pull_request"]))
        extra = "action: %s" % data["action"]

    elif event_type == "pull_request_review":
        p_info = pretty_pr(pr_from_event_data(repo, data["pull_request"]))
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


def event_handler(event_type, data):
    """Everything start here"""
    integration = github.GithubIntegration(config.INTEGRATION_ID,
                                           config.PRIVATE_KEY)
    token = integration.get_access_token(data["installation"]["id"]).token
    g = github.Github(token)

    user = g.get_user(data["repository"]["owner"]["login"])
    repo = user.get_repo(data["repository"]["name"])

    log_formated_event(repo, event_type, data)

    ident = pending_pull_ident(data["repository"]["owner"]["login"],
                               data["repository"]["name"])
    pending_pulls = pending_pulls_get(repo, ident)

    if pending_pulls:
        for branch, p in pending_pulls.items():
            LOG.info("%s expected, sha %s", pretty_pr(p), p.head.sha)

    if event_type == "refresh":
        handle_refresh(repo, ident, pending_pulls, data)

    elif event_type == "status":
        handle_status(repo, ident, pending_pulls, data)

        # Someone closed the pending pull request without merging
    elif event_type == "pull_request":
        handle_pull_request(repo, ident, pending_pulls, data)

    elif event_type == "pull_request_review":
        handle_pull_request_review(repo, ident, pending_pulls, data)


def error_handler(job, *exc_info):
    LOG.error("event handler failure", exc_info=exc_info)


def main():
    utils.setup_logging()
    if config.FLUSH_REDIS_ON_STARTUP:
        utils.get_redis().flushall()
    with rq.Connection(utils.get_redis()):
        worker = rq.worker.HerokuWorker([rq.Queue('default')],
                                        exception_handlers=[error_handler])
        worker.work()


if __name__ == '__main__':
    main()
