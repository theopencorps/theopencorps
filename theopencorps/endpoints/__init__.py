"""
Base for API access to endpoints

None of the Python wrappers have the functionality we want, and GAE is a
bit funny about requests module etc.

We can also make use of the google Asynchronous URLFetch service to optimise
transfers.
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
import logging

from google.appengine.api import urlfetch

_MY_APP = 'TheOpenCorps/1.0.0'

class HTTPException(Exception):
    """Base class for all HTTP related exceptions"""
    pass

class cache(object):    # pylint: disable=invalid-name
    """
    Decorator to memoise return value (no kword args)
    """
    def __init__(self, func):
        self._func = func
        self.memo = {}

    def __call__(self, *args):
        if args not in self.memo:
            self.memo[args] = self._func(*args)
        return self.memo[args]

def auth(method):
    """
    Decorator to ensure we're logged in for API access where login is required
    """
    def _wrapper(*args):
        self = args[0]
        if self.token is None:
            self.login()
        return method(*args)
    return _wrapper

class ASyncResult(object):
    """
    Convenience mechanism for un-wrapping an RPC
    """
    def __init__(self, rpc, log, valid_codes=(200,)):
        self.rpc = rpc
        self.log = log
        self.valid_codes = valid_codes

    def get_result(self):
        try:
            result = self.rpc.get_result()
        except urlfetch.DownloadError as e:
            self.log.error("Failed to retrieve %s (%s)", self.rpc.msg, repr(e))
            return None

        msg = "{} {} (returned {} bytes)".format(self.rpc.msg,
                                                 result.status_code,
                                                 len(result.content))
        json_result = json.loads(result.content)

        if result.status_code in self.valid_codes:
            self.log.debug(msg)
            self.log.debug(json.dumps(
                json_result, sort_keys=True, indent=4, separators=(',', ': ')))
        else:
            self.log.warning(msg)
            self.log.info(json.dumps(
                json_result, sort_keys=True, indent=4, separators=(',', ': ')))

        return json_result


class ASyncJSONObject(ASyncResult):
    """
    This is an object we can return that appears to be a JSON entity.

    In practice, we return a future which is retrieved only when the result
    is attmepted to be manipulated, allowing easy parallelisation.
    """
    def __init__(self, *args, **kwargs):
        ASyncResult.__init__(self, *args, **kwargs)
        self._retrieved = False
        self._result = None

    def get_result(self):
        if self._retrieved:
            return
        self._result = ASyncResult.get_result(self)
        self._retrieved = True

    def __nonzero__(self):
        self.get_result()
        try:
            return self._result.__nonzero__()
        except AttributeError:
            return len(self._result) != 0

    def __len__(self):
        self.get_result()
        return self._result.__len__()

    def __getitem__(self, key):
        self.get_result()
        return self._result.__getitem__(key)

    def __getattr__(self, name):
        """Forward everything else on to our result object"""
        self.get_result()
        return getattr(self._result, name)



class APIEndpointBase(object):

    """
    Assumes JSON encoded responses
    """

    _endpoint = ""
    _accept = ""

    def __init__(self):
        self._token = None
        self.log = logging.getLogger(self.__class__.__name__)

    @property
    def token(self):
        return self._token

    @token.setter
    def token(self, token):
        if self._token is not None:
            self.log.error("Token has been set multiple times")
            self.log.debug("Before: %s, after: %s",
                           repr(self._token), repr(token))
        self._token = token

    # pylint: disable=too-many-arguments
    def _create_request_args(self, payload=None,
                                   method="GET",
                                   headers=None,
                                   allow_truncated=False,
                                   follow_redirects=True,
                                   deadline=None,
                                   validate_certificate=None):
        """
        Build up headers and perform any manipulation required on the request
        keyword arguments...
        """
        request_args = {
            "payload"                   : payload,
            "method"                    : method,
            "headers"                   : headers,
            "allow_truncated"           : allow_truncated,
            "follow_redirects"          : follow_redirects,
            "validate_certificate"      : validate_certificate}

        if request_args['headers'] is None:
            request_args['headers'] = {}

        # Deadline is optional for async requests
        if deadline is not None:
            request_args["deadline"] = deadline

        # Add our own headers
        if "User-Agent" not in request_args['headers']:
            request_args['headers']["User-Agent"] = _MY_APP
        if self._accept and "Accept" not in request_args['headers']:
            request_args['headers']["Accept"] = self._accept
        if self._token and "Authorization" not in request_args['headers']:
            request_args['headers']["Authorization"] = "token %s" % self._token
        if request_args['payload'] is not None and \
                                "Content-Type" not in request_args['headers']:
            request_args['headers']["Content-Type"] = "application/json"
        return request_args

    def request(self, resource, **kwargs):
        """
        Convenience for making requests

        Synchronous returns an object with status_code and content members.

        FIXME this should really return JSON to match ASync
        """
        request_args = self._create_request_args(**kwargs)
        result = urlfetch.fetch(self._endpoint + resource, **request_args)

        msg = "%s: %s%s %d (returned %d bytes)" % (
            request_args["method"], self._endpoint, resource,
            result.status_code, len(result.content))

        if result.status_code == 200:
            self.log.info(msg)
            self.log.debug("Sent: %s", repr(request_args["headers"]))
            self.log.debug("payload: %s", repr(request_args["payload"]))
            self.log.debug("Got:  %s", repr(result.content))
        else:
            self.log.warning(msg)
            self.log.info("Sent %s", repr(request_args["headers"]))
            self.log.debug("payload: %s", repr(request_args["payload"]))
            self.log.info(result.content)
        return result


    def request_async(self, resource, **kwargs):
        """
        Convenience for making requests

        Returns ASyncResult object, for which the JSON can
        be retrieved in the future using get_result()
        """
        request_args = self._create_request_args(**kwargs)
        rpc = urlfetch.create_rpc()
        rpc.msg = "%s: %s%s" % (request_args["method"],
                                self._endpoint,
                                resource)
        urlfetch.make_fetch_call(rpc, self._endpoint + resource, **request_args)
        return ASyncResult(rpc, self.log)


    def request_json(self, resource, valid_codes=(200,), **kwargs):
        """
        Returns a JSON-like object which is actually a future...
        """
        request_args = self._create_request_args(**kwargs)
        rpc = urlfetch.create_rpc()
        rpc.msg = "%s: %s%s" % (request_args["method"],
                                self._endpoint,
                                resource)
        urlfetch.make_fetch_call(rpc, self._endpoint+resource, **request_args)
        return ASyncJSONObject(rpc, self.log, valid_codes=valid_codes)
