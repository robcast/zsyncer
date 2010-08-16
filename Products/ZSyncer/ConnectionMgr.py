#
#    Copyright (c) 2004, Corporation of Balclutha.
#
#    Please report any bugs or errors in this program to our bugtracker
#    at http://www.last-bastion.net/HelpDesk
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
from time import time
from httplib import HTTPConnection, HTTPSConnection, FakeSocket, _CS_IDLE
from urllib import urlencode
import cPickle, re, sys, traceback, socket, base64
from threading import Lock

import Config

url_re = re.compile(r'^([a-z]+)://([A-Za-z0-9._-]+)(:[0-9]+)?')

#
# note each boundary in the body has -- prepended, and another --
# ending the set.
# the LF's are also important, but may also need \r if dealing with M$
#

# this is for easy manipulation of headers and future extensibility
headers = {
    "Content-type": "multipart/form-data; boundary=------------------------31936188043903",
    #"Accept": "text/plain",
    "keep-alive": 0,
    }

# this is passed to ZSyncer::call_
body = """--------------------------31936188043903
content-disposition: form-data; name="request"

%s
--------------------------31936188043903--
"""

#
# monkey patch connection to include timeouts ...
#

def http_connect(self):
    """Connect to the host and port specified in __init__."""
    msg = "getaddrinfo returns an empty list"
    for res in socket.getaddrinfo(self.host, self.port, 0,
                                  socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        try:
            self.sock = socket.socket(af, socktype, proto)
            # Python 2.3 has this new feature but it's not exposed in any
            # of the socket API's :(   Also, there's possibly some NAF
            # stuff going on whereby some implementations don't yet have
            # it ...
            try:
                self.sock.settimeout(Config.timeout)
            except:
                _debug_print(self, "could not set socket timeout to %s"
                             % Config.timeout)
            _debug_print(self, "connect: (%s, %s)" % (self.host, self.port))
            self.sock.connect(sa)
        except socket.error, msg:
            _debug_print(self, "connect fail: (%s, %s)"
                         % (self.host, self.port))
            if self.sock:
                self.sock.close()
            self.sock = None
            continue
        break
    if not self.sock:
        raise socket.error, msg

def https_connect(self):
    "Connect to a host on a given (SSL) port."

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Python 2.3 has this new feature but it's not exposed in any
    # of the socket API's :(   Also, there's possibly some NAF
    # stuff going on whereby some implementations don't yet have
    # it ...
    try:
        sock.settimeout(Config.timeout)
    except:
        _debug_print(self, "could not set socket timeout to %s"
                     % Config.timeout)
    sock.connect((self.host, self.port))
    ssl = socket.ssl(sock, self.key_file, self.cert_file)
    self.sock = FakeSocket(sock, ssl)


# MonkeyPatch HTTPConnection and HTTPSConnection to
# get timeouts.
HTTPConnection.connect = http_connect
HTTPSConnection.connect = https_connect
 
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
        if user:
            self.headers = dict(headers)
            self.headers["Authorization"] = "Basic %s" % base64.encodestring(
                "%s:%s" % (user, password))
        else:
            self.headers = headers
            
        self.method = method
        try:
            proto, host, port = url_re.match(url).groups()
            if port:
                port = int(port[1:])   # remove the ':' ...
        except:
            raise AttributeError, 'Invalid URL: %s' % url

        assert proto in ('http', 'https'), 'Unsupported Protocol: %s' % proto
        if proto == 'http':
            self._v_conn = HTTPConnection(host, port or 80)
        else:
            self._v_conn = HTTPSConnection(host, port or 443)

    def __call__(self, *args, **kw):
        try:
            self._lock.acquire()
            try:
                call_info = cPickle.dumps((self.method, args, kw), 1)
                self._v_conn.request('POST', self.url, body % call_info,
                                     self.headers)
                response = self._v_conn.getresponse()
            except:
                raise
            data = response.read()
            if response.status >= 400:
                msg = '%s: %i - %s\n%s' % (self.url, response.status,
                                           response.reason, data)
                raise IOError, msg
            ok,rd = cPickle.loads(data)
            if ok:
                return rd
            raise rd[0], rd[1]
        finally:
            # force connection state - think there could be a bug in httplib...
            try:
                self._v_conn._HTTPConnection__state = _CS_IDLE
                self._v_conn._HTTPConnection__response.close()
            except:
                pass
            self._lock.release()

    def __del__(self):
        try:
            self._v_conn.close()
        except:
            pass

# Some logging to stdout. 
def _debug_print(self, msg):
    if self.debuglevel > 0:
        sys.stderr.write(msg + '\n')


