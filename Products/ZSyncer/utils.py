"""
Utility classes & functions for ZSyncer and UIs.
"""

# Std. lib imports.
import types

# Zope imports.
import Acquisition
from Acquisition import aq_base
from AccessControl import ClassSecurityInfo
import DateTime
from DateTime.DateTime import DateTimeError
from DocumentTemplate.DT_Util import html_quote
import Globals

# ZSyncer imports.
import Config

class ZSyncerConfigError(Exception):

    """There is a problem with the configuration of this ZSyncer.
    """

class ZSyncerObjNotFound(Exception):

    """ZSyncer could not find an object at the path.
    """


##########################################################################
# Logging & UI messages
##########################################################################

class TextMsg:

    """For logging & output of arbitrary text.
    """

    color = 'black'
    status = 200

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return str(self.msg)

    def html(self):
        return '<div style="color: %s">%s</div>\n' % (self.color,
                                                      html_quote(self.msg))


class StatusMsg(TextMsg): #, Acquisition.Implicit):

    """For logging & output of remote call results.
    """

    def __init__(self, msg, status, context=None):
        """msg may be a text string or a TextMsg.
        """
        status = int(status)
        if isinstance(msg, TextMsg):
            msg = msg.msg
        self.status = status
        if status == 200:
            self.color = Config.color_200
            if not msg.startswith('OK'):
                msg = 'OK: %s' % msg
            self.msg = msg
        else:
            self.color = Config.color_error
            self.msg = '%s: %s' % (Config.error_messages.get(str(status),
                                                             'Unknown error!'),
                                   msg)

    def __eq__(self, other):
        # Useful for testing.
        return (other.msg == self.msg and other.status == self.status)

    def __repr__(self):
        # Useful for testing.
        return '%s("%s", %s)' % (self.__class__.__name__,
                               self.msg, self.status)

# This is necessary in order to use the Msg classes in untrusted code.
from Products.PythonScripts.Utility import allow_class
allow_class(StatusMsg)
allow_class(TextMsg)


############################################################################
# Utility classes & functions
############################################################################

def normalizeRelativeURL(url):
    """
    utility function - does basically what os.path.normpath()
    does for filesystem paths, but for URLs instead.
    Does not verify whether anything exists at the path.
    """
    if not isinstance(url, types.StringType):
        raise TypeError
    url = url.strip()
    elements = url.split('/')
    if not elements:
        return '/'
    norm_elements = []
    for e in elements:
        e = e.strip()
        if e in ('', '.'):
            continue
        elif e == '..':
            try:
                norm_elements.pop()
            except IndexError:
                continue
        else:
            norm_elements.append(e)
    result = '/'.join(norm_elements)
    # We've thrown away any leading slashes, so put one back if needed.
    if url and url[0] == '/':
        result = '/' + result
    return result


def isZClassFolder(obj):
    base_obj = aq_base(obj)
    is_zclass = (getattr(base_obj, 'meta_type', None) == 'Z Class'
                 and getattr(base_obj, 'propertysheets', None)
                 and getattr(base_obj.propertysheets, 'methods', None)
                 )
    return not not is_zclass  # boolean hack for compatibility with py 2.1

def lstrip(astring, prefix=' '):
    """Workaround for the fact that ''.lstrip() takes no arguments in
    python 2.1.

    This can be deleted and replaced with ''.lstrip() once we require
    zope 2.7.
    """
    pre_len = len(prefix)
    while prefix and astring[:pre_len] == prefix:
        astring = astring[pre_len:]
    return astring

def normalize_time(datetime):
    """Convert datetime to string representing time in local zone.

    The datetime arg can be either a string parsable by
    DateTime.DateTime(), or it can already be a DateTime instance.

    Output is sort of like that used by ls -l 
    (i.e. only show year if it's not this year), e.g.:
    'Aug  5  2003' or 'Sep 21 23:22'.

    If the input is a string that cannot be parsed, return ''.
    """

    # XXX I wanted to have it possible to pass a timezone string
    # like "UTC" and see the time represented in that zone,
    # but this does not work because DateTime().strftime() 
    # always shows you the result in the local timezone regardless 
    # of the args used to construct the DateTime instance. 
    # The methods with names ending in Z do preserve the timezone,
    # but you have no real control over the output format. Bah. 
    # There does not seem to be any good solution.

    if type(datetime) is types.StringType:
        try:
            datetime = DateTime.DateTime(datetime)
        except DateTimeError:
            return ''
    ##show_zone = zone
    ##zone = zone or DateTime().localZone()
    ##datetime = DateTime(datetime, zone)
    # show year, and no hour/minute, if the day is not in this year.
    if not datetime.isCurrentYear():
        fmt = r'%b %d, %Y'
    else:
        fmt = r'%b %d %H:%M'
        # Timezone only makes sense if we're showing hour/minute.
        # XXX aargh, we cannot control the timezone displayed, see above.
        ##if show_zone:
        ##    fmt = fmt + r' %Z'
    return datetime.strftime(fmt)


def listSyncers(context):
    """Get a list of dicts representing all acquirable syncers.
    Useful for ZMI 'sync' tab.

    Dictionary keys are: 'url', 'syncer'.
    """
    zsyncers = context.superValues('ZSyncer')
    tools = context.superValues('Portal ZSyncer Tool')
    for tool in tools:
        zsyncers.extend(tool.objectValues('ZSyncer'))
    urls = []
    for zs in zsyncers:
        try:
            rel_path = '/'.join(zs._getRelativePhysicalPath(context, strict=1))
        except ValueError:
            # The context is not within the base path of that
            # syncer, so, skip it.
            continue
        url = '%s/manage_sync?folder=%s' % (zs.absolute_url(),
                                            rel_path)
        urls.append({'syncer': zs, 'url': url})
    return urls


