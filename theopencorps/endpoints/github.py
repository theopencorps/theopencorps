"""
Lightweight wrapper around the GitHub API for use in GAE
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

import base64
import json

from theopencorps.endpoints import APIEndpointBase, HTTPException, cache


class GithubEndpoint(APIEndpointBase):

    _endpoint = "https://api.github.com"
    _accept = "application/vnd.github.v3+json"

    def __init__(self, token=None):
        APIEndpointBase.__init__(self)
        self.token = token
        self.log.info("Created endpoint with token %s", repr(token))

    @property
    @cache
    def user(self):
        """
        Get the currently logged in user
        """
        return json.loads(self.request("/user").content)


    def get_repos(self):
        username = self.user["login"]
        self.log.info("Fetching repos for %s", username)
        return json.loads(self.request("/users/%s/repos" % username).content)

    def get_repo_async(self, user, repo):
        return self.request_async("/repos/%s/%s" % (user, repo))


    def get_repo(self, user, repo):
        response = self.request("/repos/%s/%s" % (user, repo))
        if response.status_code != 200:
            raise HTTPException("Attempt to retrieverepo info  %s/%s returned %d (%s)",
                                user, repo,
                                response.status_code, response.content)
        return json.loads(response.content)


    def get_file(self, user, repo, path):
        response = self.request("/repos/%s/%s/contents/%s" % (user, repo, path))
        if response.status_code != 200:
            raise HTTPException("Attempt to retrieve %s/%s/%s returned %d (%s)",
                                user, repo, path,
                                response.status_code, response.content)
        response = json.loads(response.content)
        assert response['encoding'] == "base64"
        return base64.b64decode(response['content'])


    def fork(self, user, repo, organisation="", block=True):
        """
        Fork a repo

        If block, wait until the new repository is available and
        return the new repository information
        """
        if not block:
            raise NotImplementedError("Haven't implemented non-blocking fork yet")
        if organisation:
            payload = json.dumps({"organization": organisation})
            fullname = "%s/%s" % (organisation, repo)
        else:
            payload = None
            fullname = "%s/%s" % (self.user["login"], repo)
        result = self.request("/repos/%s/%s/forks" % (user, repo),
                              method="POST",
                              payload=payload)
        if result.status_code != 202:
            raise HTTPException("Attempt to create fork of %s/%s returned %d (%s)",
                                user, repo,
                                result.status_code, result.content)

        self.log.info("Forking %s/%s to %s returned %d",
                      user, repo, fullname, result.status_code)

        return json.loads(result.content)

    # pylint: disable=too-many-arguments
    def create_webhook(self, user, repo, url,
                       events=("push",), secret="bingo", insecure=True):
        """
        Create a webhook on a given repository
        """
        payload = {
            "name" :    "web",
            "active":   True,
            "events":   events,
            "config":   {
                "url":          url,
                "content_type": "json",
                "secret":       secret,
                }
            }

        # Currenyly github doesn't seem to like let's encrypt
        if insecure:
            payload["config"]["insecure_ssl"] = "1"

        response = self.request("/repos/%s/%s/hooks" % (user, repo),
                                method="POST",
                                payload=json.dumps(payload))

        if response.status_code != 201:
            raise HTTPException("Attempt to create webhook on %s/%s returned %d (%s)",
                                user, repo,
                                response.status_code, response.content)
        return True

    def get_head(self, user, repo, branch='master'):
        """
        Find the SHA1 of the tip of selected branch
        """

        response = self.request("/repos/%s/%s/git/refs/heads/%s" % (user, repo, branch))
        if response.status_code != 200:
            return None
        current = json.loads(response.content)
        return current["object"]["sha"]

    # pylint: disable=too-many-arguments
    def commit_file(self, user, repo, path, content, message,
                    branch='master'):
        """
        Commit a file
            path        (str)   path to file
            content     (str)   file contents
            message     (str)   commit message
        """
        # Find the SHA1 of the existing file, if it exists
        response = self.request("/repos/%s/%s/contents/%s" % (user, repo, path),
                                payload=json.dumps({
                                    "path"      : path,
                                    "ref"       : branch}))
        if response.status_code == 404:
            sha1 = None
        else:
            current = json.loads(response.content)
            sha1 = current['sha']

        parameters = {
            "path"      : path,
            "message"   : message,
            "branch"    : branch,
            "content"   : base64.b64encode(content),
            "committer": {
                "name"  : self.user['name'],
                "email" : self.user['email'],
                },
            }
        if sha1 is not None:
            parameters['sha'] = sha1

        response = self.request("/repos/%s/%s/contents/%s" % (user, repo, path),
                                payload=json.dumps(parameters),
                                method="PUT")
        if sha1 is None:
            return response.status_code == 201
        return response.status_code == 200


    # pylint: disable=too-many-arguments
    def cherry_pick(self, user, repo, sha1, branch="master", force=False):
        """
        Cherry pick an sha1 onto user/repo

        Returns the sha if something was merged
        or False if not
        """
        result = self.request("/repos/%s/%s/git/refs/heads/%s" % (user, repo, branch),
                              method="PATCH",
                              payload=json.dumps({"sha": sha1, "force": force}))
        msg = "%s/%s <- %s" % (user, repo, sha1)
        if result.status_code == 200:
            self.log.info("Cherry-picked %s", msg)
            return sha1
        raise HTTPException("Cherry-pick failed: %s (%d)", msg, result.status_code)

    def merge(self, user, repo, sha1, base="master"):
        """
        Merge an sha1 into user/repo

        Returns the sha if something was merged
        or False if not
        """
        result = self.request("/repos/%s/%s/merges" % (user, repo),
                              method="POST",
                              payload=json.dumps({
                                "base"      : base,
                                "head"      : sha1}))
        msg = "%s/%s <- %s" % (user, repo, sha1)

        mapping = {201: "successful", 202: "accepted", 204: "no-op"}
        if result.status_code in mapping:
            self.log.info("Merge %s (%s)", mapping[result.status_code], msg)
            sha = ""
            try:
                content = json.loads(result.content)
                sha = content["sha"]
                self.log.info("Merge commit was %s", sha)
            except Exception as e:
                self.log.error("Unable to extract sha from %s (%s)",
                               repr(content), repr(e))
            return sha

        if result.status_code == 409:
            self.log.warning("Merge conflict! (%s)", msg)
        elif result.status_code == 404:
            self.log.warning("Merge base or head doesn't exist! (%s)", msg)
        else:
            self.log.warning("Unknown status %d (%s) -> %s", result.status_code, msg, result.content)

        raise HTTPException("Merge attempt failed: %s (%d)", msg, result.status_code)

