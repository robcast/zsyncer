"""
ZSyncer

A Zope product that provides a synchronization service
to copy (and compare) objects from one Zope server to another.

Home page:    http://zsyncer.sourceforge.net
Release version: see version.txt
Instructions:    see README.txt
Copyright:       see LICENSE.txt
Authors:         see credits.txt
Changelog:       see changes.txt
Future Plans:    see TODO.txt

"""
# $Id: ZSyncer.py,v 1.104 2009/10/23 16:32:11 slinkp Exp $

# Stdlib imports
import logging
import os
import sys
import tempfile
import time
import traceback
import types
import urllib
import urlparse
from cStringIO import StringIO

# Zope imports
import OFS.SimpleItem
import Acquisition
import AccessControl.Role
import OFS.PropertyManager
from AccessControl import getSecurityManager
from AccessControl import ClassSecurityInfo
from AccessControl import Unauthorized
from Acquisition import aq_parent, aq_inner, aq_base
from DateTime import DateTime
from App.special_dtml import DTMLFile
from App.Dialogs import MessageDialog
from Persistence import Persistent
from App.class_init import InitializeClass
from OFS.Traversable import NotFound
from Products.PageTemplates.PageTemplateFile import PageTemplateFile

from webdav.interfaces import IWriteLock

# Imports for rpc using ZPublisher.Client.
from cPickle import loads, dumps
from ZPublisher import Client
from ZODB.POSException import ConflictError


# Imports for diff.
from OFS.History import html_diff, replace
from string import join, split, atoi, strip

# ZSyncer imports.
import Config
from ConnectionMgr import _MethodProxy as _ConnectionMgrMethodProxy
from utils import ZSyncerConfigError, ZSyncerObjNotFound
from utils import TextMsg, StatusMsg
import utils

# imports for CMF if available.
try:
    from Products.CMFDefault.DublinCore import DefaultDublinCoreImpl
except ImportError:
    DefaultDublinCoreImpl = None

# Constants.
from Config import OK
from Config import EXTRA
from Config import MISSING
from Config import OOD

# BBB: Using logging in Zope 2.7 requires the name to begin with 'event'.
# We can change that to just 'ZSyncer' if/when we no longer support 2.7.
logger = logging.getLogger('event.ZSyncer')

ZSYNC_PERMISSION = "ZSyncer: Use ZSyncer"
MGT_SCR_PERMISSION = 'View management screens'

manage_addZSyncerForm = DTMLFile('dtml/Add', globals())

def manage_addZSyncer(self, id='', title='', REQUEST=None):
    """Adds a ZSyncer instance.
    """
    self._setObject(id, ZSyncer(id, title))
    if REQUEST is not None:
        return MessageDialog(title = 'Added',
                             message = "ZSyncer sucessfully added.",
                             action = 'manage_main', )


class ZSyncer(OFS.SimpleItem.Item, Persistent, Acquisition.Implicit,
              AccessControl.Role.RoleManager,
              OFS.PropertyManager.PropertyManager):

    """A service provider that allows you to 'push' objects
    from one running Zope to another across the network.
    You need one instance on both the source and destination servers.
    """

    meta_type = 'ZSyncer'
    security = ClassSecurityInfo()
    manage_options = (
        {'label': 'Properties', 'action': 'manage_propertiesForm',
         'help':('ZSyncer', 'ZSyncer.stx') },
        {'label': 'Sync', 'action': 'manage_sync',
         'help':('ZSyncer', 'ZSyncer.stx') },
        {'label': 'Undo', 'action': 'manage_UndoForm',
         'help':('OFSP', 'Undo.stx') },
        {'label': 'Ownership', 'action': 'manage_owner',
         'help':('OFSP', 'Ownership.stx') },
        {'label': 'Security', 'action': 'manage_access',
         'help':('OFSP', 'Security.stx') },
    ) 

    _properties=(
        {'id':'title', 'type':'string', 'mode':'w'},
        {'id':'dest_servers', 'type':'lines', 'mode':'w'},
        {'id':'log', 'type':'boolean', 'mode':'w'},
        {'id':'logfile', 'type':'string', 'mode':'w'},
        {'id':'approval', 'type':'boolean', 'mode':'w'},
        {'id':'syncable', 'type':'multiple selection', 'mode':'w',
         'select_variable': 'syncable'},
        {'id':'use_relative_paths', 'type':'boolean', 'mode':'w'},
        {'id':'relative_path_base', 'type':'string', 'mode':'w'},
        {'id':'strip_talkback_comments', 'type':'boolean', 'mode':'w'},
        {'id':'add_syncable', 'type':'lines', 'mode':'w'},
        {'id':'connection_type', 'type':'string', 'mode':'w'},
        {'id':'filterObjects', 'type':'boolean', 'mode': 'w'},
        {'id':'filterOutObjects', 'type':'boolean', 'mode': 'w'},
        {'id':'non_syncable', 'type':'lines', 'mode':'w'},

        )

    # Some immutable class-level defaults.
    # ... these help with upgrading old instances.
    filterObjects = 0
    filterOutObjects = 0
    add_syncable = ()
    non_syncable = ()
    use_relative_paths = 0
    relative_path_base = ''
    strip_talkback_comments = 0
    connection_type = 'ConnectionMgr' #'ZPublisher.Client'

    security.declareProtected(ZSYNC_PERMISSION,
                              'manage_addProperty',
                              'manage_editProperties',
                              'manage_delProperties',
                              'manage_changeProperties'
                              )

    security.declareProtected(MGT_SCR_PERMISSION,
                              'manage_tabs',
                              'manage_propertiesForm')
    # manage_main has beed replaced with manage_propertiesForm.
    manage_propertiesForm = DTMLFile('dtml/Edit', globals())

    security.declareProtected(MGT_SCR_PERMISSION, 'manage_sync')
    manage_sync = DTMLFile('dtml/Sync', globals())

    security.declareProtected(MGT_SCR_PERMISSION, 'manage_approval')
    manage_approval = DTMLFile('dtml/Approval', globals())

    security.declareProtected(MGT_SCR_PERMISSION, 'manage_diff')
    manage_diff = PageTemplateFile('www/Diff', globals())

    security.declareProtected(MGT_SCR_PERMISSION, 'manage_folders')
    manage_folders = DTMLFile('dtml/Folder', globals())


    # Immutable default attributes for upgrades.
    syncable = tuple(Config.syncable)
    dest_servers = ()

    def __init__(self, id, title=''):
        """initialize a new instance of Server
        """
        self.id = id
        self.title = title
        #self.source_server = [ None, ]  # Source is this Syncer. XXX unused?
        self.dest_servers = [ ]
        self.log = 0
        self.approval = 0
        self.syncable = Config.syncable[:]
        self.logfile = os.path.join('log', 'ZSyncer.log')
        self.connection_type = 'ConnectionMgr' # 'ZPublisher.Client'
        self.use_relative_paths = 1
        self.strip_talkback_comments = 0
        self.filterObjects = 0
        self.filterOutObjects = 0
        self.add_syncable=[]
        self.non_syncable = []

    security.declareProtected(MGT_SCR_PERMISSION, 'manage_approvedAction') 
    def manage_approvedAction(self, REQUEST={}, action='',
                              folder=None,
                              object_paths=None, syncer=None, approver=None,
                              comments=''):
        """If this action is to be approved, throw that data in
        into the message list
        """
        msgs = ['User: %s' % syncer,]
        if self.approval:
            msgs.append('Approved by: %s' % approver)
        # Strip out any newlines in comments.
        comments = comments.replace('\n', '')
        msgs.append('Comments: %s' % comments)
        # Call the relevant thing.
        folder = (folder or REQUEST.get('folder', '')).strip()
        action = (action or REQUEST.get('action', '')).strip().lower()
        if action.count('put'):
            return self.manage_pushToRemote(object_paths, msgs=msgs,
                                            REQUEST=REQUEST)
        elif action.count('delete'):
            return self.manage_syncDelete(object_paths, msgs=msgs,
                                          REQUEST=REQUEST)
        elif action.count('get'):
            return self.manage_pullFromRemote(object_paths,
                                              msgs=msgs, REQUEST=REQUEST)
        elif action.count('touch'):
            return self.manage_touch(object_paths, msgs=msgs, REQUEST=REQUEST)
        else:
            return self._error(msg='Unknown action')

    security.declareProtected(ZSYNC_PERMISSION, 'manage_syncDelete')
    def manage_syncDelete(self, object_paths, msgs=None, REQUEST=None):
        """
        Interface to deleting both locally and remotely.
        object_paths may be a string or a sequence of strings.
        If msgs list is provided, it's modified in-place;
        it's also returned.
        """
        if msgs is None:
            msgs = []
        if type(object_paths) is types.StringType:
            object_paths = [object_paths,]
        self.manage_deleteRemote(object_paths, msgs, REQUEST=None)
        for path in object_paths:
            status = self.manage_replaceObject(path, None)
            msgs.append(StatusMsg('Deleting %s locally' % str(path), status))
        self._do_messages(msgs, REQUEST)
        return msgs

    security.declareProtected(ZSYNC_PERMISSION, 'manage_deleteRemote')
    def manage_deleteRemote(self, object_paths, msgs=None, REQUEST=None):
        """Interface to calling delete on each destination server.
        """
        if msgs is None:
            msgs = []
        if type(object_paths) is types.StringType:
            object_paths = [object_paths,]
        for object_id in object_paths:
            for srv in self.dest_servers:
                text = 'Object %s deleting from %s' % (object_id, srv)
                status = self._deleteRemote(srv, object_id)
                msgs.append(StatusMsg(text, status))
            if not self.dest_servers:
                # No destination servers configured!
                msgs.append(StatusMsg("Can't delete %s, "
                                      "No destination servers configured" %
                                      object_id,
                                      500)
                            )
        self._do_messages(msgs, REQUEST)
        return msgs

    security.declareProtected(ZSYNC_PERMISSION, 'manage_touch')
    def manage_touch(self, object_paths, msgs=None, REQUEST=None):
        """
        Force timestamp of local and remote object(s) to *now*.
        A list of StatusMsgs or TextMsgs will be returned.
        """
        if type(object_paths) is types.StringType:
            object_paths = [object_paths]
        if msgs is None:
            msgs = []
        timestamp = DateTime()
        remote_methods = []
        for object_path in object_paths:
            self.touch(object_path, timestamp)
            msgs.append(StatusMsg("Object %s touched locally." % object_path,
                                  200))
            method_info = {'name': 'touch',
                           'args': [object_path, timestamp]}
            remote_methods.append(method_info)
        # Do remote calls efficiently.
        # This will either succeed, or raise exceptions.
        self.callManyRemote(remote_methods)
        msgs.extend([StatusMsg('Object %s touched remotely' % p,  200)
                     for p in object_paths])
        self._do_messages(msgs, REQUEST)
        return msgs

    security.declareProtected(ZSYNC_PERMISSION, 'manage_pushToRemote')
    def manage_pushToRemote(self, object_paths, msgs=None, REQUEST=None):
        """Interface to pushing each object to destination
        server.

        The 'msgs' argument may be modified in-place, and will be
        returned as a list of TextMsg or StatusMsg instances.
        """
        if type(object_paths) is types.StringType:

            object_paths = [object_paths,]
        if msgs is None:
            msgs = []
        # Stream the output using http 1.1 chunking.  Doesn't actually
        # stream when behind Apache, but neither did the old
        # guesstimate-content-length hack.
        # XXX Is it possible w/ javascript to force browser to scroll
        # down?  Be sure to log something even if syncing fails.
        if REQUEST and self.log:
            user = getSecurityManager().getUser()
            self._log('%s attempting to sync %s' % (user, object_paths))
        self._msg_header(REQUEST=REQUEST)
        # Handle user & approver comments, or anything else
        # already in the msgs argument.
        for m in msgs:
            self._do_one_msg(TextMsg(m), REQUEST)
        # Sync.
        for object_path in object_paths:
            try:
                data = self.manage_getExportData(object_path)
            except ZSyncerObjNotFound:
                msg =  StatusMsg('cannot push %s' % object_path,
                                 404)
                msgs.append(msg)
                self._do_one_msg(msg, REQUEST)
                break
            for srv in self.dest_servers:
                status = self._exportToRemote(srv, object_path, data)
                msg = StatusMsg('Object %s to %s' % (object_path, srv),
                                status)
                msgs.append(msg)
                self._do_one_msg(msg, REQUEST)
        self._msg_footer(REQUEST)
        return msgs

    security.declareProtected(ZSYNC_PERMISSION, 'manage_pullFromRemote')
    def manage_pullFromRemote(self, object_paths, msgs=None,
                              REQUEST=None):
        """Interface to retrieving each object from destination
        server.
        """
        if type(object_paths) is types.StringType:
            object_paths = [object_paths]
        if msgs is None:
            msgs = []
        # Just grab it from the first successfully connectable dest server.
        serverconn = None
        for srv in self.dest_servers:
            try:
                serverconn = self._getServerConn(srv)
                break
            except:
                err = 'Error in manage_pullFromRemote connecting to %s' % srv
                self._logException(err)
                continue
        if serverconn is None:
            raise ZSyncerConfigError, "Unable to connect to any server"
        self._msg_header(REQUEST=REQUEST)
        self._do_one_msg(TextMsg('Getting objects from server %s' %
                                 srv),
                         REQUEST)
        for obj_path in object_paths:
            id_msg = TextMsg('Getting "%s"...' % obj_path)
            self._do_one_msg(id_msg, REQUEST)
            try:
                # We can't fix up the path because we might not have
                # the object locally.
                data = serverconn.manage_getExportData(obj_path)
            except:
                # object is Missing?
                err = 'ERROR pulling %s' % obj_path
                self._logException(err)
                msg = StatusMsg('%s: check log for info' %  err, 500)
                msgs.append(msg)
                self._do_one_msg(msg, REQUEST)
            else:
                self.manage_replaceObject(obj_path, data)
                msg = StatusMsg('%s downloaded' % obj_path, 200)
                msgs.append(msg)
                self._do_one_msg(msg, REQUEST)
        self._msg_footer(REQUEST)
        return msgs

    security.declareProtected(ZSYNC_PERMISSION, 'manage_diffObject')
    def manage_diffObject(self, object_path, REQUEST=None):
        """Try to get the object from the destination server
        and diff on it.
        Return the result as a dictionary.
        """
        error = ''
        source = self.manage_getSource(object_path)
        dest_server = self._getFirstDestination()
        try:
            dest = self._srcRemote(dest_server, object_path)
        except:
            # XXX except what???
            # Historically, non-ascii chars prevent diffing.
            # Was this an artifact of XML-RPC? Test again with ZPub.Client
            # or ConnectionManager.
            self._logException('Exception in manage_diffObject')
            error = "Couldn't get source of remote object - "
            error +="it might contain non-ASCII values?" 
            dest = ''
        # Check result, there should be a better way to do this using raise, 
        # oh well.
        if type(source) is types.IntType:
            error = StatusMsg("Getting local source:", source).html()
        if type(dest) is types.IntType:
            error = StatusMsg("Getting remote source:", dest).html()
        if error:
            diff = ''
        else:
            diff = html_diff(dest, source)
        return {'diff': diff, 'source': source, 'dest': dest, 'error': error}

    security.declareProtected(MGT_SCR_PERMISSION, 'manage_compare')
    def manage_compare(self, path, recurse=None, REQUEST=None):
        '''Compare items, optionally recursing into subfolders;
        optionally filtering by status according to REQUEST.
        Return a tuple of (dict, [list of dicts]) where
        the first dict represents the status of the object at *path*,
        and the dicts in the (possibly empty) list represent the
        status of sub-objects of that object.

        If *recurse* is true, subobjects of subfolders are merged and
        flattened into the subs list.

        The list is sorted by path.

        If the list is empty, it means the remote server found no sub-objects
        at *path*.
        '''
        if REQUEST is not None:
            allowed_status = REQUEST.get('show_status', None)
        else:
            allowed_status = None
        results = self._compare_path(path, recurse=recurse,
                                     REQUEST=REQUEST,
                                     include_base=1)
        # Filter once after getting all results.
        if allowed_status:
            filtered = [r for r in results[1] if r['status'] in allowed_status]
        else:
            filtered = results[1]
        # Sort by path.
        sortable = [('/'.join(f['path']), f) for f in filtered]
        sortable.sort()
        final = (results[0], [s[1] for s in sortable])
        return final

    security.declareProtected(MGT_SCR_PERMISSION, 'manage_getSource')
    def manage_getSource(self, obj_path):
        """Get a src from an object (if allowed) suitable for diffing.
        """
        try:
            obj = self._getObject(obj_path)
        except ZSyncerObjNotFound:
            return 404

        c = getSecurityManager().checkPermission
        if not c(MGT_SCR_PERMISSION, obj):
            return 403
        # Try to handle various kinds of objects;
        # use whatever's in the config for this meta_type.
        base_obj = aq_base(obj)
        mt = base_obj.meta_type
        attrname = Config.diff_methods.get(mt, Config.diff_methods['DEFAULT'])
        diff_attr = getattr(base_obj, attrname)
        if callable(diff_attr):
            src = diff_attr()
        else:
            src = diff_attr
        return src

    security.declareProtected(ZSYNC_PERMISSION, 'manage_replaceObject')
    def manage_replaceObject(self, obj_path, data=None):
        """
        If an object already exists at *obj_path*,  delete it.
        If *data* is not None, treat is as a picked new object to
        add at that path.
        """
        try:
            obj_path = self._getRelativePhysicalPath(obj_path)
        except (ValueError, NotFound, ZSyncerObjNotFound):
            # The object was not found or is not within the root path.
            # That's a problem when we're deleting.  But if *data* is
            # provided, this just means we're adding a new object.
            if data:
                pass
            else:
                return 404
        if not obj_path:
            raise ValueError, "Need a non-empty object path"
        if type(obj_path) is types.StringType:
            obj_path_printable = obj_path
            obj_path = obj_path.split('/')
        else:
            obj_path_printable = '/'.join(obj_path)
        root = self._getSyncerRoot()
        if len(obj_path) == 1:
            # The object goes in our root.
            obj_parent = root
        else:
            # We already know length is non-zero, so there must be
            # some subfolders on the path. They must correspond to
            # subfolders of root and not be acquired from above
            # (or from siblings). So, we walk the path by hand,
            # instead of using (un)restrictedTraverse.
            obj_parent = root
            try:
                for segment in obj_path[:-1]:
                    obj_parent = obj_parent[segment]
            except KeyError:
                return 404
        # Let's check the user is allowed to do this.
        checkPermission = getSecurityManager().checkPermission
        allowed = 1
        for perm in ['Delete objects', 'Import/Export objects']:
            if not checkPermission(perm, obj_parent):
                allowed = 0
        if not allowed:
            return 403

        # If the obj_parent supports ordering, note the old object's position
        # so that we can move the new object to that position.
        position = None
        obj_parent_base = aq_base(obj_parent)
        isBTreeFolder = getattr(obj_parent_base, '_tree', None) != None
        # Check for Zope 2.7+ OrderSupport (or Archetypes OrderedBaseFolder),
        # but avoid BTreeFolders.
        has_order_support = getattr(obj_parent_base, 'moveObjectsByDelta',
                                    0) and not isBTreeFolder
        # Check for OrderedObjectManager monkey patch, but avoid BTreeFolders.
        has_ordered_object_manager = getattr(
            obj_parent_base, 'move_objects_by_positions', None) \
            and not isBTreeFolder
        # If there is one there already, delete it.
        # Hooray for transactions :)
        if ((obj_path[-1] in obj_parent.objectIds())
                # ZClass propertysheets.methods ids might have a trailing space
                or [id for id in obj_parent.objectIds() \
                        if id.strip() == obj_path[-1]]):
            # Fix ordering.
            if has_order_support:
                position = obj_parent.getObjectPosition(obj_path[-1])
            elif has_ordered_object_manager:
                position = obj_parent.get_object_position(obj_path[-1])
            obj_parent.manage_delObjects([obj_path[-1],])
        else:
            if data is None:  # Ok if we are deleting.
                return 404
        # Add the new object, if any.
        if data is not None:
            logger.debug('trying to import %s **', obj_path_printable)
            threshold = Config.upload_threshold_kbytes * 1024
            # Write the data either to a temporary file, or hold it in RAM.
            if len(data) < threshold:
                _file = StringIO()
            else:
                _file = tempfile.TemporaryFile()
            _file.write(data)
            del(data)
            _file.seek(0)
            # Now import it.
            try:
                new_obj = obj_parent._p_jar.importFile(_file)
            except:
                # We'll re-raise it.
                msg = '_p_Jar.importFile(_file) failed '
                msg += '... receiving %s' % obj_path_printable
                logger.error(msg)
                raise
            _file.close()
            if new_obj == None:
                msg = ('importing %s failed, problem with parents?' %
                       obj_path_printable)
                logger.error(msg)
                raise AttributeError, msg
            object_id = new_obj.getId()
            try:
                obj_parent._setObject(object_id, new_obj)
            except:
                # we'll re-raise it.
                msg = 'obj_parent._setObject failed '
                msg += '...receiving %s' % obj_path_printable
                logger.error(msg)
                raise

            # Fix OrderedFolder position.
            if(position is not None):
                try:
                    methodname = 'moveObjectToPosition'
                    if has_order_support:
                        obj_parent.moveObjectToPosition(object_id, position)
                    elif has_ordered_object_manager:
                        methodname = 'move_objects_by_positions'
                        newposition = obj_parent.get_object_position(object_id)
                        obj_parent.move_objects_by_positions(object_id,
                                                         position-newposition)
                except:
                    # We'll re-raise it.
                    msg = 'obj_parent.%s failed ' % methodname
                    msg += '...receiving %s' % obj_path_printable
                    logger.error(msg)
                    raise
            # SF bug 988027:
            # Clear DAV locks, if any.
            lockmanager = self.Control_Panel.DavLocks
            new_obj = obj_parent[object_id]
            # Clear only from this object and any subobjects.
            if (getattr(aq_base(new_obj), 'isPrincipiaFolderish', 0)
                or utils.isZClassFolder(new_obj)
                ):
                newpath = '/'.join(new_obj.getPhysicalPath())
                locked_paths = [p[0] for p in
                                lockmanager.findLockedObjects(newpath)]
                if locked_paths:
                    logger.debug('clearing DAV locks from %s\n', locked_paths)
                    lockmanager.unlockObjects(paths=locked_paths)
            elif IWriteLock.providedBy(aq_base(new_obj)):
                new_obj.wl_clearLocks()
        if self.strip_talkback_comments:
            logger.debug('manage_replaceObject deleting coments under%s\n',
                         obj_path_printable)
            utils.kill_talkback_comments(obj_parent)
        # Success!
        logger.debug('manage_replaceObject succeeded at %s\n',
                     obj_path_printable)
        return 200

    security.declareProtected(MGT_SCR_PERMISSION, 'status_colour')
    def status_colour(self, status, default="white"):
        '''Gives a list of status colours for pretty html.
        '''
        return Config.colours.get(status, default)

    security.declareProtected(MGT_SCR_PERMISSION, 'status_descr')
    def status_descr(self, status):
        '''Get description of each status from the config.
        '''
        return Config.descriptions.get(status,
                                       Config.descriptions.get('default', ''))

    def status_icon(self, status):
        """Get icon of each status from the config.
        """
        path =  Config.icons.get(status, None)
        if not path:
            return ''
        rootpath = self.getPhysicalRoot().absolute_url_path()
        path = rootpath + '/' + path
        path = path.replace('//', '/')
        return path  #self.absolute_url_path() + '/' + path

    security.declareProtected(MGT_SCR_PERMISSION, 'manage_listObjects')
    def manage_listObjects(self, path, do_base=1):
        """Gets status information for an objectManager on this server.
        (No remote calls.)

        Object information is represented by dictionaries.

        The result is organized as a pair of (d1, d2) where d1 is a
        dictionary representing the object at *path* itself, and d2 is
        a dictionary keyed by the folder's subobjects' ids, where each
        value is a dict containing information for one subobject.

        If *do_base* is false, the first element (d1) will be empty.
        """
        subobj_dicts = {}
        # Go find the object at the path.
        path = self._getRelativePhysicalPath(path)
        path_object = self.traverseFromRoot(path)
        if do_base and self._isComparisonAllowed(path_object):
            obj_info = self._getInfoForObject(path_object)
        else:
            obj_info = {}
        # Get the sub-objects.
        if getattr(aq_base(path_object), 'isPrincipiaFolderish', 0):
            sub_objects = path_object.objectValues()
        elif utils.isZClassFolder(path_object):
            sub_objects = path_object.propertysheets.methods.objectValues()
        else:
            sub_objects = []
        for ob in sub_objects:
            # We don't sync ZSyncers, that way leads to much confusion
            # so we'll just sync objects we know work.
            # Also avoid broken objects.
            # Allow people to turn this feature on and off.
            if not self._isComparisonAllowed(ob):
                continue
            o = self._getInfoForObject(ob)
            subobj_dicts[o['id']] = o
        return (obj_info, subobj_dicts)

    def _isComparisonAllowed(self, obj):
        """Return true of obj is something we are able to compare.
        """
        if self.filterObjects and not obj.meta_type in self.syncable:
            return 0
        elif self.filterOutObjects and obj.meta_type in self.non_syncable:
            return 0
        elif obj.meta_type.startswith('Broken Because'):
            return 0
        elif self._isReserved(obj):
            return 0
        else:
            return 1

    def _getInfoForObject(self, obj):
        """Get a dictionary of information about one object.
        """
        d = {}
        d['id'] = obj.getId()
        d['path'] = self._getRelativePhysicalPath(obj)
        # Various URLs useful for UI.
        d.update(self.getPathInfo(d['path']))
        # This should always be a string right?
        d['meta_type'] = obj.meta_type
        icon = obj.icon
        if not isinstance(icon, types.StringType):
            # CMF fix, where apparently obj.icon may be callable.
            icon = icon()
        if not icon.startswith('/'):
            # Avoid stupid relative paths, don't want to download
            # the icons again in every folder.
            icon = '%s/%s' % (obj.getPhysicalRoot().absolute_url_path(), icon)
        d['icon'] = icon.replace('//', '/')
        d['is_folder'] = getattr(obj, 'isPrincipiaFolderish', 0)
        # Try to get DublinCore mod time, if available.
        base_obj = aq_base(obj)
        if DefaultDublinCoreImpl is not None and \
               isinstance(base_obj, DefaultDublinCoreImpl):
            d['dc_modtime'] = base_obj.modified()
        else:
            d['dc_modtime'] = ''
        # Formerly known as 'modtime'... this is a DateTime instance.
        bobotime = obj.bobobase_modification_time()
        d['last_modified_time'] = bobotime
        # Size in kB. For backward compatibility, don't depend
        # on this.
        try:
            d['size'] = int(obj.get_size()) / 1024
        except AttributeError:
            d['size'] = ''
        return d

    security.declarePrivate('is_diffable')
    def is_diffable(self, meta_type=None, status=OK):
        '''Do we know how to render a diff for this type?
        and, is its status such that we *can* show a diff for it?
        '''
        if meta_type not in Config.diffable:
            return 0
        elif status in (MISSING, EXTRA):
            return 0
        else:
            return 1

    security.declareProtected(ZSYNC_PERMISSION, 'getPathInfo')
    def getPathInfo(self, path):
        """Useful for building UIs.  Should NOT raise errors.

        Returns a dictionary with the following keys/values:

          'absolute_url_path':
             absolute_url_path of the object.
             If the object is not found, assume it's an 'extra' object;
             then full == original path.

          'relative_path':
             string path to the object, relative to this zsyncer's container.
             If the object is not found, assume it's an 'extra' object;
             in that case, relative == original path.

          'id_or_path':
             string path relative to REQUEST['folder'] if REQUEST['recursive']
             is true; otherwise, id (the final path element).
        """
        if type(path) is not types.StringType:
            path = '/'.join(path)
        try:
            relative = '/'.join(self._getRelativePhysicalPath(path))
        except (ZSyncerObjNotFound, ValueError):
            # maybe Extra.
            relative = path
        try:
            obj = self.traverseFromRoot(relative)
        except ZSyncerObjNotFound:  #(KeyError, NotFound):
            # No object found, maybe Extra. Fall back to the original.
            full = relative = path
            obj = None
        if obj is not None:
            # Get the full path according to the object itself.
            full = obj.absolute_url_path()
        request = self.REQUEST
        if request.get('mode') == 'recursive':
            if request.get('folder', '') != '':
                # Use the relative path but without the folder.
                if self.use_relative_paths:
                    prefix = utils.lstrip(request['folder'], '/') + '/'
                else:
                    prefix = request['folder'] + '/'
                id_or_path = utils.lstrip(relative, prefix)
            else:
                # We're in the root folder. Doing the above replacement would
                # remove all slashes from the path!
                id_or_path = relative
        else:
            # Just the id.
            id_or_path = relative.split('/')[-1]

        return {'absolute_url_path': full,
                'relative_path': relative,
                'id_or_path': id_or_path
                }


    #### Diagnostic helpers #################

    security.declareProtected(ZSYNC_PERMISSION, 'getErrorAdvice')
    def getErrorAdvice(self, error_type, error_value):
        """Given an error_type and error_value,
        say something helpful :-)

        This is a bit hacky because of having two connection methods
        that do different things.
        """
        error_value = str(error_value)
        error_type = str(error_type)

        # Connection Refused
        if error_value.count('Connection refused'):
            msgs = ['Check that the destination server is running.',
                    'Check that routing, firewall etc. allows http ' \
                    'connections to %s' % self._getFirstDestination(),
                    ]
        else:
            msgs = ['The remote syncer is responding, but...']
        # Not Found
        if error_value.count('NotFound') or \
               error_value.count('Not Found'):
            msgs += ['Check that the destination zsyncer is really there at '+
                    '"%s."' % self._getFirstDestination()]
        # UNAUTHORIZED
        elif error_value.count('401 Unauthorized'):
            # That works for both connection types.
            msgs.extend(['Check that the user exists on destination server',
                         'Check the password on the destination server',
                         'Check the user has permission to use ZSyncer on'
                         ' destination server',
                         ]
                        )
        # You're inside a missing folder.
        elif error_type == 'KeyError' or \
                 error_value.count('KeyError'):
            msgs+=["The folder you're in may be missing on destination server",
                   'Try going up to the parent folder and sync it from there.']
        # No idea.
        else:
            msgs += ['Unexpected problem, maybe on the remote server.' \
                     " See below, and check the destination's error log."]
        return msgs


    ########################################################################
    # Internal methods, not part of the API.
    ########################################################################

    def _isReserved(self, ob):
        # Is the object something we should not sync?
        path = ob.getPhysicalPath()
        # don't sync yourself.
        if path == self.getPhysicalPath():
            return 1
        # names from the config.
        if len(path) == 2 and path[1] in Config.reserved_names:
            return 1
        else:
            return 0


    #################################################################
    # COMPARISONS
    #################################################################

    def _get_status(self, s_item, d_item):
        '''Compare two dicts representing syncable object information,
        decide what the status is, and create a composite dict with
        all info needed for display.

        Returns (status as a string, itemdict)
        '''
        s_item = s_item or {}  # The 'source' item.
        d_item = d_item or {}  # The 'destination' item.
        item = {}
        # Need at least one non-None and non-empty argument.
        if not s_item and not d_item:
            msg =  "_get_status got two null args! '%s' and '%s'" % (
                str(s_item), str(d_item))
            raise ValueError, msg
        # Start looking for status.
        if not d_item:
            item = s_item.copy()
            item['status'] = MISSING
        elif not s_item:
            item = d_item.copy()
            item['status'] = EXTRA
        else:
            item = s_item.copy()
        # Get mod times.
        # bobobase_modification_times suck, but sometimes it's all we have.
        s_bobotime = s_item.get('last_modified_time', '')
        d_bobotime = d_item.get('last_modified_time', '')
        item['dest_mod_time'] = d_bobotime
        item['src_mod_time'] = s_bobotime
        # See if we have DublinCore metadata times available.
        s_dc_modtime = s_item.get('dc_modtime', '')
        d_dc_modtime = d_item.get('dc_modtime', '')
        # Decide which timestamp to use by default for display,
        # and format them. May be empty string if we don't get
        # any usable date (e.g. if there's no object at that path).
        item['dest_best_modtime'] = utils.normalize_time(
                d_dc_modtime or d_bobotime)
        item['src_best_modtime'] = utils.normalize_time(
            s_dc_modtime or s_bobotime)
        # If status is already set, we're done.
        if item.get('status') is None:
            # Compare timestamps. Note that DC timestamps MUST compare equal,
            # but bobobase timestamps are allowed some fuzziness.
            if s_dc_modtime and d_dc_modtime:
                if s_dc_modtime == d_dc_modtime:
                    item['status'] = OK
                else:
                    # XXX FIXME- for DC we should really treat < and >
                    # differently, which would require adding another status.
                    item['status'] = OOD
            # Last resort, use bobobase_modification_time.
            elif s_bobotime.timeTime() - d_bobotime.timeTime() < \
                     Config.fudge_secs:
                item['status'] = OK
            else:
                item['status'] = OOD
        # It's handy to include the color and icon here.
        item['status_color'] = self.status_colour(item['status'])
        item['status_icon'] = self.status_icon(item['status'])
        return (item['status'], item)

    def _getFirstDestination(self):
        """Get the first remote server, for comparisons.
        If there are none, raise ZSyncerConfigError.

        XXX we should ideally allow the user to choose which
        server to use, instead of forcing it to be the top one.
        """
        try:
            remote = self.dest_servers[0]
        except IndexError:
            raise ZSyncerConfigError, "No remote servers are configured."
        return remote

    def _compare_path(self, path, recurse=None, REQUEST=None,
                      include_base=None):
        """Get the local and remote status for everything at and below
        the path, optionally recursing into folders. Result is NOT
        filtered by status.

        Returns a tuple of (dict, [list of dicts])
        where the first item represents the object at *path*
        and the list represents its sub-objects. Each dictionary
        represents one compared object.

        If *include_base* is false, the first dict in the tuple
        will be empty.

        Should *not* raise ZSyncerObjNotFound UNLESS no information
        is obtainable with the given args; this means the status
        is neither Extra nor Missing, it's simply not found anywhere.
        that really is an exceptional condition!
        Should never come up in the UI since you shouldn't be able
        to browse to such a non-existent object.
        """
        compared = []
        try:
            path = '/'.join(self._getRelativePhysicalPath(path))
        except ZSyncerObjNotFound:
            # Can't find the local object, so hopefully path is OK for remote.
            pass
        # Get the remote stuff.
        remote = self._getFirstDestination()
        try:
            dest_base_info, dest_sub_info = self._getRemoteList(remote, path)
        except ZSyncerObjNotFound:
            dest_base_info = {}
            dest_sub_info = {}
        # Get the local stuff.
        try:
            # Even though we may not use it, we need to get info for
            # the base object so we know whether it's found.
            local_base_info, local_sub_info = self.manage_listObjects(path, 1)
        except ZSyncerObjNotFound:
            local_base_info = {}
            local_sub_info = {}
        # At minimum, we need base info SOMEWHERE.
        if not (local_base_info or dest_base_info):
            errmsg = "Nothing at %s on local OR destination!" % path
            raise ZSyncerObjNotFound, errmsg
        if include_base:
            base_status, base_item = self._get_status(local_base_info,
                                                      dest_base_info)
            base_item['is_diffable'] = self.is_diffable(
                status=base_status,
                meta_type=base_item['meta_type']
                )
        else:
            # We won't use it anyway.
            base_item = {}
        # Make a set of all keys from either server.
        all_keys = {}
        for k in local_sub_info.keys() + dest_sub_info.keys():
            all_keys[k] = None
        for key in all_keys.keys():
            local_dict = local_sub_info.get(key, {})
            remote_dict = dest_sub_info.get(key, {})
            status, item = self._get_status(local_dict, remote_dict)
            item['is_diffable'] = self.is_diffable(status=item['status'],
                                                   meta_type=item['meta_type'],
                                                   )
            compared.append(item)
            if not recurse:
                continue
            # Recursing...
            if item['is_folder'] and status not in (MISSING, EXTRA):
                sub_path = utils.normalizeRelativeURL('/'.join(item['path']))
                # Never recurse back into yourself!
                if path == sub_path:
                    continue
                #OK, really recurse, but don't filter.
                try:
                    logger.debug("recursing FROM %s\n TO %s", path, sub_path)
                    # XXX Optimization: This is very inefficient use
                    # of network!  We have to fire off a request to
                    # the remote server for each subfolder. Ouch!
                    # Would be better if _getRemoteList took a
                    # recursion argument and passed it along to
                    # manage_listObjects, which should take care of
                    # the recursion.
                    results = self._compare_path(path=sub_path,
                                                 recurse=recurse,
                                                 REQUEST=REQUEST,
                                                 include_base=None)
                    results = results[1]
                except Unauthorized:
                    logger.debug("got Unauthorized at %s", path)
                    results = []
                compared.extend(results)
        output = (base_item, compared)
        return output

    #####################################################################
    #  MESSAGES AND LOGGING
    #####################################################################

    def _error(self, code=None, msg=None):
        # Error handling for UI.
        if msg is None and code is not None:
            msg = Config.error_messages.get(code, 'Unknown error occured')
        return MessageDialog(title='Message', message=msg,
                             action='manage_main')

    def _get_time(self):
        # Get time for logging.
        # Could be done using DateTime, but i think I want to fiddle this.
        return time.asctime(time.localtime(time.time()))

    def _do_messages(self, msgs, REQUEST=None):
        """Log a list of messages, and if there is a REQUEST, do an
        html display.
        """
        do_log = self.log or self.approval
        do_html = REQUEST is not None
        ms = []
        self._msg_header(REQUEST)
        processed_msgs = []
        for m in msgs:
            if isinstance(m, TextMsg):
                processed_msgs.append(m)
            elif type(m) is types.IntType:
                # We no longer support the old hack where
                # an integer meant "combine me with the previous
                # message to make a new StatusMsg".
                raise TypeError, "%d passed to _do_messages" % m
            else:
                # Presumably something we can wrap in a TextMsg.
                processed_msgs.append(TextMsg(m))
        for m in processed_msgs:
            self._do_one_msg(m, REQUEST)
        self._msg_footer(REQUEST)
        return processed_msgs

    def _msg_header(self, REQUEST=None):
        '''Writes log and/or html info at beginning of a sync.
        '''
        if REQUEST is not None:
            # Be sure we have enough content-length... overestimate.
            REQUEST.RESPONSE.setHeader('content-type', 'text/html')
            head ='''
            <html><body><form action="%s/manage_sync" method="GET">
            <input type="hidden" name="folder"
             value="%s">''' % (self.absolute_url_path(),
                               self.REQUEST.get('folder', '/'))

            REQUEST.RESPONSE.write(head)
        if self.log or self.approval:
            self._log(' -------  Started syncing. -------')

    def _msg_footer(self, REQUEST):
        if REQUEST is not None:
            foot = '''<div>
                <b>DONE!</b>
                <br />
                <input type="submit" value=" OK ">
                </div>
                </form></body></html>
            '''
            REQUEST.RESPONSE.write(foot)
        if self.log or self.approval:
            self._log('Done')

    def _do_one_msg(self, msg, REQUEST=None):
        """Log and/or display a single Msg.
        """
        if self.log or self.approval:
            self._log(msg)
        if REQUEST is None:
            return 0
        # Now stream it.
        html = msg.html()
        REQUEST.RESPONSE.write(html)
        REQUEST.RESPONSE.flush()

    def _log(self, msgs):
        # Log messages for ZSyncer.
        # This will become more configurable.
        m_time = self._get_time()
        try:
            aq_base(self)._v_logfile
        except AttributeError:
            if self.logfile.startswith('/'):
                msg = 'You have set an absolute path to the log file for your'
                msg += ' ZSyncer instance at '
                msg += '/'.join(self.getPhysicalPath())
                msg += '. You should probably make it relative to your'
                msg += ' instance home.'
                logger.error(msg)
            path = os.path.join(INSTANCE_HOME, self.logfile)
            self._v_logfile = open(path, 'a')
        self._v_logfile.write('%s\t%s\n' % (m_time, str(msgs)))
        self._v_logfile.flush()

    def _logException(self, msgs):
        # Log the latest traceback.
        if not self.log:
            return
        exc = '\n'.join(traceback.format_exception(*sys.exc_info()))
        msgs = '%s %s' % (msgs, exc)
        self._log(msgs)

    ######################################################################
    # Control of the remote server
    #####################################################################

    def _getServerConn(self, server_url):
        """Get a connection to the server.
        OK to leave off http://
        """
        if server_url[:7] != 'http://' and server_url[:8] != 'https://':
            server_url = 'http://%s' % server_url
        if server_url[:5] != 'http:' and server_url[:6] != 'https:':
            server_url = 'http:%s' % server_url
        proto, netloc, url, params, query, fragment = urlparse.urlparse(
            server_url)
        # Not all the transports are bright enough to handle basic
        # auth URL syntax, so we parse them out of the URL and cook up
        # the proper headers.
        auth, host = urllib.splituser(netloc)
        if auth is not None:
            user, pwd = auth.split(':')
        else:
            # No auth info provided in the URL, so we fall back to
            # using the current effective user and assume it exists on
            # the remote server.
            u = getSecurityManager().getUser()
            user, pwd = u.getId(), u._getPassword()
        url = urlparse.urlunparse((proto, host, url, params, query,
                                   fragment))
        conn_type = self.connection_type
        if conn_type == 'ZPublisher.Client':
            server = _ZPCServer(server=url, user=user, passwd=pwd)
        elif conn_type == 'ConnectionMgr':
            server = _ConnectionMgrServer(server=url, user=user, passwd=pwd)
        else:
            raise ValueError, "unknown connection type %s" % conn_type
        return server

    def _getRemoteList(self, server_url, path):
        '''Get the list of remote stuff,
        in the format used by manage_compare.
        '''
        serverconn = self._getServerConn(server_url)
        return serverconn.manage_listObjects(path)

    def _srcRemote(self, server_url, object_path):
        """Get the source text of the remote object.
        """
        serverconn = self._getServerConn(server_url)
        return serverconn.manage_getSource(object_path)

    def _deleteRemote(self, server_url, object_path):
        """Delete an object on the remote server.
        """
        # XXX This should be changed to accept a list of objects
        # so we can delete them all in one transaction.
        serverconn = self._getServerConn(server_url)
        try:
            result = serverconn.manage_replaceObject(object_path, None)
        except:
            # XXX except what???
            self._logException('Exception in _deleteRemote')
            result = 500
        return result

    security.declareProtected(ZSYNC_PERMISSION, 'touch')
    def touch(self, object_path, timestamp=DateTime()):
        """
        Force timestamp update to the (local) object.
        Optional timestamp arg must be a DateTime instance,
        and is set to the object's modification_date attribute
        IFF it has one.
        """
        assert isinstance(timestamp, DateTime), \
               'invalid timestamp: %s' % type(timestamp)
        ob = self.traverseFromRoot(object_path)
        # Can't call isinstance() on an ExtensionClass, so 
        # we check if the object looks like DefaultDublinCoreImpl.
        marker = []
        if getattr(aq_base(ob), 'modification_date', marker) is not marker:
            ob.modification_date = timestamp
        # Force zodb timestamp update.
        ob._p_changed = 1

    def _touchRemote(self, server_url, object_path, timestamp=DateTime()):
        """Touches an object on the remote server.
        """
        serverconn = self._getServerConn(server_url)
        try:
            serverconn.touch(object_path, timestamp)
            result = 200
        except:
            # XXX except what???
            self._logException('Exception in _touchRemote')
            result = 500
        return result

    security.declareProtected(ZSYNC_PERMISSION, 'manage_getExportData')
    def manage_getExportData(self, path):
        """Gets data suitable for transfer.
        """
        path = self._getRelativePhysicalPath(path)  # XXX
        obj = self._getObject(path)
        data = StringIO()  # XXX this might eat a lot of memory.
        obj._p_jar.exportFile(obj._p_oid, data)
        return data.getvalue()

    def _exportToRemote(self, server_url, path, data):
        """Adds a copy of the pickled 'data' object to the remote server.
        """
        serverconn = self._getServerConn(server_url)
        obj_path = self._getRelativePhysicalPath(path)
        # OK, export to the destination.
        try:
            result = serverconn.manage_replaceObject(obj_path, data)
        except:
            # XXX except what???
            self._logException('Exception in _exportToRemote')
            result = 500

        return result

    ###############################################################
    # GENERIC RPC SUPPORT - CLIENT SIDE
    ###############################################################

    security.declareProtected(ZSYNC_PERMISSION, 'callRemote')
    def callRemote(self, server_url, path, method_name, *args, **kw):
        """Find an arbitrary callable at *path* on the remote server,
        call it with the given arguments, and return the result.

        If *path* is None, it's the remote syncer itself.
        """
        # XXX Other methods could be refactored to use this one.
        server = self._getServerConn(server_url)
        result = server.callMethod_(path, method_name, *args, **kw)
        return result

    security.declareProtected(ZSYNC_PERMISSION, 'callManyRemote')
    def callManyRemote(self, methodlist):
        """Call multiple remote methods and return a list of
        return values, using as few requests as possible.

        methodlist should be a sequence of dictionaries with the following
        keys:

          'path': (optional): path to the object on which to call the method,
           relative to the remote syncer's base. If not provided,
           the zsyncer itself is used.

          'name': name of the method.

          'args' (optional): list of positional arguments to pass.

          'kwargs' (optional): dictionary of keyword arguments to pass.

        """
        # XXX Need to stream messages if remote methods are slow.
        # XXX Other methods could be refactored to use this one.
        results = []
        for server_url in self.dest_servers:
            server = self._getServerConn(server_url)
            results.extend(server.callMethods_(methodlist))
        return results

    ###############################################################
    # GENERIC RPC SUPPORT - SERVER SIDE
    ###############################################################

    security.declareProtected(ZSYNC_PERMISSION, 'callMethod_')
    def callMethod_(self, path, method_name, *args, **kw):
        """Call an arbitrary method (with security checks).
        *path* is path to the object. If it is None,
        the zsyncer itself will be used.

        *method_name* is method to call. Any result is returned.

        This is intended to be called by the client zsyncer, ONLY via
        callRemote(), but there is no way to enforce that.

        Note that for security reasons, you must have permission to
        use ZSyncer *and* to call the requested method in context.
        """
        # XXX Look for server-side methods which can be replaced
        # with calls to this.
        if path is None:
            obj = self
        else:
            obj = self.traverseFromRoot(path)
        method = getattr(obj, method_name)
        sm = getSecurityManager()
        if not sm.validate(self, self, method_name, method):
            user = sm.getUser().getId()
            err ="User %s is not allowed to call %s here" % (user,
                                                             method_name)
            raise Unauthorized, err
        result = method(*args, **kw)
        return result

    security.declareProtected(ZSYNC_PERMISSION, 'callMethods_')
    def callMethods_(self, methodlist):
        """Call a list of arbitrary methods (with security checks).
        Return a list of results.

        *methodlist* is a list of dictionaries with these keys:

          'path': path to the object on which to call the method,
           relative to the base folder. (optional, defaults to the
           syncer itself).

          'name': name of the method.

          'args' (optional): list of positional arguments to pass.

          'kwargs' (optional): dictionary of keyword arguments to pass.

        This is intended to be called by the client zsyncer,
        ONLY via callManyRemote(), but there is no way to enforce that.

        Note that for security reasons, you must have permission
        to use ZSyncer *and* to call all the requested methods in
        context.
        """
        # XXX Look for server-side methods which can be replaced
        # with calls to this.
        results = []
        for info in methodlist:
            path = info.get('path')
            name = info['name']
            args = info.get('args', [])
            kwargs = info.get('kwargs', {})
            results.append(self.callMethod_(path, name, *args, **kwargs))
        return results


    ###################################################################
    # Local object and path helpers
    ###################################################################

    security.declareProtected(ZSYNC_PERMISSION, 'getSyncerRootPath')
    def getSyncerRootPath(self):
        """
        Get path to the root to use for traversing to syncable objects,
        as a string.
        """
        if self.use_relative_paths:
            rootpath = self.relative_path_base.strip() or ''
        else:
            rootpath = '/'
        return rootpath

    security.declareProtected(ZSYNC_PERMISSION, 'getSyncerRootId')
    def getSyncerRootId(self):
        """
        Get the ID of the object to use for traversing to syncable objects.
        """
        root = self._getSyncerRoot()
        return root.getId() or 'root'

    def _getSyncerRoot(self):
        """
        Get the object to use for traversing to syncable objects.
        """
        basepath = self.getSyncerRootPath()
        if basepath:
            syncer_root = self.unrestrictedTraverse(basepath)
        else:
            # Fall back to our parent container.
            syncer_root = aq_parent(aq_inner(self))
        return aq_inner(syncer_root)  # wrapped by containment only.

    security.declareProtected(ZSYNC_PERMISSION, 'traverseFromRoot')
    def traverseFromRoot(self, relative_path):
        """
        Find an object relative to the syncer root, without using
        acquisition.

        Assume that the path has already been normalized.

        Further assume that all objects we're traversing support
        __getitem__ syntax, as does e.g. ObjectManager.

        Raises ZSyncerObjNotFound in case of failure.
        """
        if type(relative_path) is types.StringType:
            relative_path = relative_path.split('/')
        else:
            relative_path = list(relative_path)
        obj = self._getSyncerRoot()
        # Occasionally, client code passes an absolute path,
        # even if the syncer is configured to use relative paths.
        # So, left-strip that out.
        if self.use_relative_paths:
            root_path = self.getSyncerRootPath()
            temp_path = utils.lstrip('/'.join(relative_path), root_path)
            relative_path = temp_path.split('/')
        for name in relative_path:
            if name == '':
                # Empty path elements don't change anything.
                continue
            try:
                obj = obj[name]
            except (KeyError, AttributeError):
                raise ZSyncerObjNotFound, relative_path
        return obj

    def __splitAndValidatePath(self, obj_path):
        # Returns a tuple path split into (root path, object path)
        # or raises ValueError if the root is not a parent of the path.
        # (assuming the path is by containment only.)
        rootpath = self.getSyncerRootPath()
        if rootpath == '/':
            return (rootpath, obj_path)
        elif rootpath == '':
            rootpath = self._getSyncerRoot().getPhysicalPath()
        else:
            rootpath = tuple(rootpath.split('/'))
        if obj_path[:len(rootpath)] != rootpath:
            msg = "'%s' not within '%s'" %('/'.join(obj_path),
                                           '/'.join(rootpath)
                                           )
            raise ValueError, msg
        return (rootpath, obj_path[len(rootpath):])

    def _getObject(self, path):
        """
        Get an object at the given path (which must be relative
        to the syncer root).

        Raises ZSyncerObjNotFound if no object is found.

        Should NOT acquire things above the syncer root; raises
        ValueError if an attempt to do so is made.

        n.b.: use this with output from '_getRelativePhysicalPath()'.
        """
        if type(path) is types.StringType:
            path = tuple(path.strip().split('/'))
        if path[0] == '' and len(path) > 1:
            # It's an absolute path.
            rootpath, path = self.__splitAndValidatePath(path)
        else:
            pass
        obj = self.traverseFromRoot(path)
        return obj

    def _getRelativePhysicalPath(self, obj_or_path, strict=1):
        """
        Get a clean *physical* path to the object or path, either
        relative to this zsyncer's container or relative to the app root,
        depending on setting of the use_relative_paths property.

        n.b.: this is the complement of '_getObject()'.

        If *obj_or_path* is a path, it can be either a string or
        a tuple.

        Return value is a sequence of path elements, e.g.
        as returned by getPhysicalPath().

        If 'strict' is true, object must be somewhere within
        the container given by getSyncerRootPath()
        or we'll raise ValueError. True by default.

        If 'strict' is false and we're using relative paths and the
        object is not within getSyncerRootPath(), the result is
        undefined.

        If object doesn't exist, the underlying error is propagated
        (e.g. KeyError or NotFound).
        """
        # Handle various input types, get the object.
        if type(obj_or_path) in (types.TupleType, types.ListType):
            obj_or_path = '/'.join(obj_or_path)
        if type(obj_or_path) is types.StringType:
            obj = self._getObject(obj_or_path)
        else:
            obj = obj_or_path
        obj_path = obj.getPhysicalPath()
        # Are we done?
        if not self.use_relative_paths:
            return obj_path
        try:
            rootpath, obj_path = self.__splitAndValidatePath(obj_path)
        except ValueError:
            if strict:
                raise
            # otherwise, just swallow the error.
        return obj_path

    #########################################################
    # Remote ZSyncer call interface, used by MethodProxies
    #########################################################

    security.declareProtected(ZSYNC_PERMISSION, 'call_')
    def call_(self, request, REQUEST=None):
        '''
        *request* (poorly named, but changing it breaks stuff) is not
        an HTTPRequest, rather it should be a pickled tuple
        containing method_name (string), arguments (a sequence), and
        keyword arguments (a dictionary).

        Return value is a pickled tuple of (success, value) where
        success is boolean and value is the return value of
        getattr(self, method_name)(*args, **kwargs)
        '''
        # Contributed by Dieter Maurer.
        # This is only used on the remote side, and is called
        # by the configured network transport code.
        method_name, args, kw= loads(request)
        try:
            method = getattr(self, method_name)
            if not getSecurityManager().validate(self, self,
                                                 method_name, method):
                raise Unauthorized
            result = method(*args, **kw)
            ok = 1
        except ConflictError:
            # This will be retried.
            raise
        except:
            # Yes we trap all exceptions here, but we try to be very
            # informative about it.
            self._logException('Exception in call_')
            # We want to send back the exception.
            result = sys.exc_info()[:2]
            ok = 0
        return dumps((ok, result), 1)


    ############################################################
    # UPGRADE SUPPORT
    ############################################################

    security.declareProtected(MGT_SCR_PERMISSION, 'upgrade')
    def upgrade(self):
        """ upgrade from 0.5.1 (or earlier?) to current version.
        """
        out = []
        for attr in ('user', 'pwd', 'override', 'override_user'):
            if hasattr(aq_base(self), attr):
                out.append('Deleting attribute %s' % attr)
                delattr(self, attr)
        old_dest = getattr(aq_base(self), 'dest_server', None)
        if old_dest is None or self.dest_servers:
            out.append("No old destinations to fix for %s" % self.getId())
        if type(old_dest) in (types.ListType, types.TupleType):
            old_dest = list(old_dest)
        else:
            old_dest = [old_dest]
        self.dest_servers = old_dest
        self._p_changed = 1
        return '%s\nUpgraded %s OK' % ('\n'.join(out), self.getId())


InitializeClass(ZSyncer)

######################################################################
# Classes for various transports avoiding XML-RPC
######################################################################

class _BaseServer:

    '''Auxiliary class to call the server.
    Derived classes should define __getattr__(self, method). 
    '''

    def __init__(self, server, user, passwd):
        '''
        server: url of server to connect to, including path to ZSyncer
        user:  user id
        passwd: plain-text passwd
        '''
        self._info = (server, user, passwd)


class _ZPCServer(_BaseServer):

    '''Auxiliary class to call the server via ZPublisher.Client.
    Used for http syncing.
    '''

    def __getattr__(self, method):
        return _ZPCMethodProxy(self._info, method)


class _ConnectionMgrServer(_BaseServer):

    '''Auxiliary class to call the server via ConnectionMgr.
    Used for http and https syncing.
    '''

    def __getattr__(self, method):
        proxy = _ConnectionMgrMethodProxy(self._info, method)
        return proxy


class _BaseMethodProxy:

    '''Wraps a method so we can call it on a remote server.
    Derived classses should define __call__(self, *args, **kw)
    '''

    def __init__(self, info, method):
        '''
        info = (server, user, password)
        method = the method to wrap
        '''
        self._info= info
        self._method= method

class _ZPCMethodProxy(_BaseMethodProxy):

    '''Wraps a method so we can call it on a remote server
    via ZPublisher.Client.
    '''

    def __call__(self, *args, **kw):
        server, user, password= self._info
        remote_function = Client.Function(server+'/call_',
                                          method= 'POST',
                                          username= user,
                                          password= password,
                                          )
        remote_function.headers['Content-Type'] = 'multipart/form-data'
        request_data = dumps((self._method, args, kw), 1)
        response_data = remote_function(request=request_data)
        ok, result = loads(response_data[1])
        if ok:
            return result
        raise result[0], result[1]


