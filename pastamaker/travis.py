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

import requests

LOG = logging.getLogger(__name__)

BASE_URL = 'https://api.travis-ci.org'
V2_HEADERS = {"Accept": "application/vnd.travis-ci.2+json",
              "User-Agent": "Pastamaker/1.0.0"}


@property
def detail(self):
    if not hasattr(self, "_pastamaker_travis_detail"):
        if not self.travis_url or self.travis_url == "#":
            self._pastamaker_travis_detail = None
            return None
        build_id = self.travis_url.split("?")[0].split("/")[-1]
        r = requests.get(BASE_URL + "/builds/" + build_id,
                         headers=V2_HEADERS)
        if r.status_code != 200:
            self._pastamaker_travis_detail = None
            return None
        build = r.json()["build"]
        build["resume_state"] = self.travis_state
        build["jobs"] = []
        for job_id in build["job_ids"]:
            r = requests.get(BASE_URL + "/jobs/%s" % job_id,
                             headers=V2_HEADERS)
            if r.status_code == 200:
                job = r.json()["job"]
                job["log_url"] = BASE_URL + "/jobs/%s/log" % job_id
                LOG.debug("%s: job %s %s -> %s" % (self.pretty(), job_id,
                                                   job["state"],
                                                   job["log_url"]))
                build["jobs"].append(job)
                if (self.travis_state == "pending" and
                        job["state"] == "started"):
                    build["resume_state"] = "working"
        LOG.debug("%s: build %s %s/%s" % (self.pretty(), build_id,
                                          build["state"],
                                          build["resume_state"]))
        self._pastamaker_travis_detail = build
    return self._pastamaker_travis_detail


def update(self, force=False):
    if force and hasattr(self, "_pastamaker_travis_detail"):
        delattr(self, "_pastamaker_travis_detail")
    return self.travis_detail


def post_report(self):
    message = ["Tests %s for HEAD %s\n" % (
        self.travis_state.upper(),
        self.head.sha)]
    for job in self.travis_detail["jobs"]:
        message.append('- [%s](%s): %s' % (
            job["config"]["env"],
            job["log_url"],
            job["state"].upper()
        ))
    message = "\n".join(message)
    LOG.debug("%s POST comment: %s" % (self.pretty(), message))
    self.create_issue_comment(message)
