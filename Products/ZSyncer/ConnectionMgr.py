#
#    Copyright (c) 2012, Corporation of Balclutha.
#
#    Please report any bugs or errors in this program to our bugtracker
#    at http://au.last-bastion.net/helpdesk
#
#    NOTE: This software is normally licensed under the GPL,
#    but Alan Miligan graciously consented to allow its use in
#    ZSyncer under the terms of the BSD license as described in
#    the accompanying LICENSE.txt.
#
#    We ask that you please contribute any changes to this file
#    back to last-bastion.net so that its authors may benefit,
#    just as you have benefited from their work,
#    in the spirit of the GPL.
#
from httplib2 import Http, ProxyInfo, BasicAuthentication
from httplib2.socks import PROXY_TYPE_HTTP
from urlparse import urlparse
import cPickle, os
from pickle import UnpicklingError
from threading import Lock
import Config


#
# note each boundary in the body has -- prepended, and another --
# ending the set.
# the LF's are also important, but may also need \r if dealing with M$
#

# this is for easy manipulation of headers and future extensibility
HEADERS = {
    "Content-type": "multipart/form-data; boundary=------------------------31936188043903",
    "Keep-Alive": "0",
    }

# this is passed to ZSyncer::call_
BODY = """--------------------------31936188043903
content-disposition: form-data; name="request"

%s
--------------------------31936188043903--
"""

 
class _MethodProxy:
    """
    Manage all HTTP connectivity

    This includes managing bandwidth and concurrency.
    This is the one-stop-shop to define and control *all*
    connectivity policy ...

    Note the use of cPickle to serialise the object ...

    This serialises all _send requests as the default policy -
    but one could easily rewrite this as a connection pool
    (which is rather the point of this class)
    """
    _lock = Lock()

    def __init__(self, info, method):
        '''
        info = (server, user, password)
        method = the method to wrap
        '''
        url, user, password = info
        self.url = "%s/call_" % url
        self.method = method
        self.headers = dict(HEADERS)
        self.auth = None

        proto = urlparse(url)[0]

        proxyinfo = None
        proxy = '%s_proxy' % proto
        
        # TODO - this could be much smarter - checking against NO_PROXY etc, but that
        # would require netmask matching and more guestimating what to do ...
        if os.environ.has_key(proxy):
            pproto, phost, directory, params, query, frag = urlparse(os.environ[proxy])
            if phost.find('@') != -1:
                pcreds, phost = phost.split('@')
                puser, ppwd = pcreds.split(':')
            else:
                puser = ppwd = None
            if phost.find(':') != -1:
                phost,pport = phost.split(':')
            elif pproto == 'https':
                pport = '443'
            else:
                pport = '80'
            if puser and ppwd:
                proxyinfo = ProxyInfo(PROXY_TYPE_HTTP, phost, int(pport), proxy_user=puser, proxy_pass=ppwd)
            else:
                proxyinfo = ProxyInfo(PROXY_TYPE_HTTP, phost, int(pport))

        self._v_conn = conn = Http(timeout=Config.timeout, proxy_info=proxyinfo)

        if user and password:
            #conn.add_credentials(user, password)
            # we *need* to force credentials into POST request, otherwise they only
            # get placed there in response to a 407 ...
            self.auth = BasicAuthentication((user, password), None, url, None, None, None, None)

        # simply ignore peer verification for now - we use http auth ;)
        conn.disable_ssl_certificate_validation = True

    def __call__(self, *args, **kw):
        try:
            self._lock.acquire()

            self.auth and self.auth.request(None, None, self.headers, None)

            response, data = self._v_conn.request(self.url, 
                                                  method='POST', 
                                                  body=BODY % cPickle.dumps((self.method, args, kw), 1),
                                                  headers=self.headers)

            if response.status >= 400:
                msg = '%s: %i - %s\n%s' % (self.url, response.status, response.reason, data)
                raise IOError, msg
            try:
                ok,rd = cPickle.loads(data)
            except Exception, e:
                raise UnpicklingError, '%s(%s) - got' % (self.url, self.method, data)
            if ok:
                return rd
            raise rd[0], rd[1]
        finally:
            self._lock.release()



