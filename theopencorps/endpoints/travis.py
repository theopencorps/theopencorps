"""
GAE does't support the existing Travis API python module, so we use a thin
wrapper on top of our generic endpoint.
"""
__copyright__ = """
Copyright (C) 2016 Potential Ventures Ltd

This file is part of theopencorps
<https://github.com/theopencorps/theopencorps/>
"""

__license__ = """
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import json
import time
import base64

import rsa

from theopencorps.endpoints import APIEndpointBase, cache, HTTPException, auth


class TravisEndpoint(APIEndpointBase):

    _endpoint = "https://api.travis-ci.org"
    _accept = "application/vnd.travis-ci.2+json"

    def __init__(self, token=None):
        APIEndpointBase.__init__(self)
        self.token = "\"%s\"" % token

    def login(self):
        if self.token is not None:
            self.log.info("Already logged into Travis with token %s", self.token)
            return

        response = self.request("/auth/github",
                                method="POST",
                                payload=json.dumps({"github_token": self.token}))
        response = json.loads(response.content)
        self.token = str(response['access_token'])
        self.log.info("Logged in to Travis (token %s)", self.token)

    def get_repo(self, user, repo):
        """
        Return a JSON object representing a repo
        """
        return self.request_json("/repos/%s/%s" % (user, repo))

    def get_build(self, build_id):
        """
        Returns a JSON object representing a build
        """
        return self.request_json("/builds/%s" % repr(build_id))

    def get_job(self, job_id):
        """
        Returns a JSON object representing a job
        """
        return self.request_json("/jobs/%s" % repr(job_id))

    @auth
    def update_settings(self, repo_id, **kwargs):
        """
        builds_only_with_travis_yml     (true or false)
        build_pushes                    (true or false)
        build_pull_requests             (true or false)
        maximum_number_of_builds        integer
        """
        response = self.request("/repos/%d/settings" % repo_id, method="PATCH",
                                payload=json.dumps({"settings": kwargs}))
        return response.status_code == 200


    @auth
    def sync(self, block=True):
        """
        If block then don't return until sync is complete

        TODO should use a future with a callback so this happens in parallel
        """
        response = self.request("/users/sync", method="POST")
        if response.status_code not in [200, 409]:
            raise HTTPException("Sync request returned %d", response.status_code)
        count = 0
        while block:
            response = json.loads(self.request("/users/").content)
            user = response['user']
            if not user['is_syncing']:
                self.log.info("Synchronised at %s after %d polls", 
                              user['synced_at'],
                              count)
                break
            # Busy waiting on an HTTP API probably isn't that friendly...
            time.sleep(0.01)
            count += 1
            if count > 50:
                raise HTTPException("Failed to sync within 0.5 seconds")

    @auth
    def is_synced(self):
        response = json.loads(self.request("/users/").content)
        user = response['user']
        if not user['is_syncing']:
            return True
        self.log.info("Still waiting for travis to synchronise")
        return False

    @auth
    def get_hooks(self):
        return self.request_json("/hooks")

    @auth
    def enable_hook(self, hook_id):
        """
        Travis falls over (500)...
        """
        # First of all try the alternative hooks API
        hook = {'active': True}
        response = self.request('/hooks/%d' % hook_id,
                                payload=json.dumps({"hook": hook}),
                                method="PUT")
        if response.status_code == 200:
            return True
        self.log.warning("PUT /hooks/%d returned %d (%s)", hook_id,
                         response.status_code, response.content)
        self.log.info("Retrying with alternative API call")
        hook = {'id': hook_id, 'active': True}
        response = self.request('/hooks',
                                payload=json.dumps({"hook": hook}),
                                method="PUT")
        if response.status_code != 200:
            raise HTTPException("Attempt to enable hook %d returned %d",
                                hook_id,
                                response.status_code)
        return True

    @auth
    @cache
    def get_key(self, owner, repo_name):
        response = json.loads(self.request('/repos/%s/%s/key' % (owner, repo_name)).content)
        return response['key']

    @auth
    def encrypt(self, owner, repo_name, string):
        """
        Encrypt a string using the repositories key

        Returns a base64 encoded string suitable for use in YML file
        """
        rsa_key = self.get_key(owner, repo_name)
        pubkey = rsa.PublicKey.load_pkcs1_openssl_pem(rsa_key)
        secure = rsa.encrypt(string.encode('utf8'), pubkey)
        return base64.b64encode(secure)

