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


import argparse
import os
import sys

import requests

from pastamaker import config
from pastamaker import utils


def main():
    parser = argparse.ArgumentParser(
        description='Force refresh of pastamaker'
    )
    parser.add_argument(
        "slug", nargs="+",
        help="<owner>/<repo>/<branch>")

    base_url = config.BASE_URL
    args = parser.parse_args()

    data = os.urandom(250)
    hmac = utils.compute_hmac(data)

    for slug in args.slug:
        url = base_url + "/refresh/" + slug
        r = requests.post(url, headers={"X-Hub-Signature": "sha1=" + hmac},
                          data=data)
        r.raise_for_status()


if __name__ == '__main__':
    sys.exit(main())
