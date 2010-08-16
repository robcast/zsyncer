""" ZSyncerTool

a CMF tool that wraps and provides a UI for ZSyncer.

Work in progress, may not actually do much yet!
"""

# Std. lib imports.
import copy

# Zope imports.
from AccessControl import ClassSecurityInfo, Permissions
from Acquisition import aq_base
from Globals import InitializeClass, DTMLFile
from OFS.SimpleItem import SimpleItem

# Third-party imports.
from Products.CMFCore.utils import UniqueObject, getToolByName

# Custom imports.
from ZSyncer import ZSyncerObjNotFound

try:
   # CMF >= 1.5
    from Products.CMFCore.permissions import ManagePortal
except ImportError:
    # CMF < 1.5
    from Products.CMFCore.CMFCorePermissions import ManagePortal

from Products.CMFCore.ActionProviderBase import ActionProviderBase
from Products.CMFCore.ActionInformation import ActionInformation
from Products.CMFCore.Expression import Expression

from OFS.Folder import Folder
from ZSyncer import ZSyncer, manage_addZSyncer, ZSYNC_PERMISSION
from ZSyncer import MISSING, EXTRA, OK, OOD
import Config

from types import StringType

_upgradePaths = {}

class ZSyncerTool(UniqueObject, Folder, ActionProviderBase):

    """
    A CMF tool that contains and provides a UI for a ZSyncer instance.

    XXX Example UI still in the early stages, it will go in skins/.
    """

    id = 'portal_zsyncer'
    meta_type = 'Portal ZSyncer Tool'
    _default_zsyncer = 'Default'

    manage_options = ActionProviderBase.manage_options + Folder.manage_options
    security = ClassSecurityInfo()

    _actions = [
       ActionInformation(
           id='zsyncer_fol_status',
           title='Sync Status',
           action=Expression(text='string: ${folder_url}/zsyncer_folderview'),
           condition=Expression(text='python: folder is object'),
           permissions=(ZSYNC_PERMISSION,),
           category='folder',
           visible=Config.show_tool_actions
           ),
       ActionInformation(
           id='zsyncer_obj_status',
           title='Sync Status',
           action=Expression(text='string: ${object_url}/zsyncer_objectview'),
	   condition=Expression(text='python: not (folder is object)'),
           permissions=(ZSYNC_PERMISSION,),
           category='object',
           visible=Config.show_tool_actions
           ),
       ActionInformation(
           id='zsyncer_diff',
           title='Diff',
           action=Expression(text='string: ${object_url}/zsyncer_diff'),
           # In the expression text, I'd like to use getToolByName(), but how??
           # Only very limited names are bound in the expression context. :-(
           condition=Expression(
               text='python:portal.portal_zsyncer.isObjectDiffable(object)'
               ),
           permissions=(ZSYNC_PERMISSION,),
           category='object',
           visible=Config.show_tool_actions
           ),
       ]

    def filtered_meta_types(self):
        """Filter meta types.
        Only ZSyncers can be added inside a ZSyncerTool.
        """
        types = Folder.filtered_meta_types(self)
        l = []
        for t in types:
            #print t['name'], ZSyncer.meta_type
            if t['name'] == ZSyncer.meta_type:
               l.append(t)
        return l

    security.declarePrivate('listActions')
    def listActions(self, info=None):
        """Return actions provided by tool.
        """
        return self._actions

    def manage_afterAdd(self, *args, **kwargs):
        """Configuration after a ZSyncerTool is added.
        """
        # add a default zSyncer
        if self._default_zsyncer not in self.objectIds():
            manage_addZSyncer(self, self._default_zsyncer)
            # Set its path to the portal root path.
            portal_path = '/'.join(self.aq_parent.getPhysicalPath())
            self[self._default_zsyncer].relative_path_base = portal_path


    ##############################################################
    # Wrappers for ZSyncer functionality
    ##############################################################

    security.declareProtected(ZSYNC_PERMISSION, 'getStatus')
    def getStatus(self, path, syncer=None, recurse=None):
        """Is this object (and subs, if any) in or out of sync?
        Result is a tuple of (info, subs), where info (and each item
        in the subs list) is a dictionary with all the useful keys.

        Also includes anything else useful for UI, e.g. actions
        we might want to link to.
        """
        syncer = self.getZSyncer(syncer)
        try:
            info, subs  = syncer.manage_compare(path, recurse)
        except ZSyncerObjNotFound:
            # No information found either remotely OR locally, ouch.
            raise
        info = self._setDefaults(info)
        info = self._setActions(info)
        subs = [self._setActions(self._setDefaults(s)) for s in subs]
        result = (info, subs)
        return result

    security.declareProtected(ZSYNC_PERMISSION, 'getDiff')
    def getDiff(self, obj_path, syncer=None):
        """Show differences for this object.
        """
        syncer = self.getZSyncer(syncer)
        return syncer.manage_diffObject(obj_path)

    security.declareProtected(ZSYNC_PERMISSION, 'obj_sync')
    def doPush(self, obj_paths, syncer=None):
        """Sync object.  Return a list of StatusMsgs.
        """
        syncer = self.getZSyncer(syncer)
        msgs = syncer.manage_pushToRemote(obj_paths)
        return msgs

    security.declareProtected(ZSYNC_PERMISSION, 'doDelete')
    def doDelete(self, obj_paths, syncer=None):
        """Delete remote AND local object.
        """
        syncer = self.getZSyncer(syncer)
        msgs = []
        syncer.manage_syncDelete(obj_paths, msgs)
        return msgs

    security.declareProtected(ZSYNC_PERMISSION, 'getDestinations')
    def getDestinations(self, syncer=None):
        """Get a list of destinations for this syncer.
        """
        syncer = self.getZSyncer(syncer)
        return syncer.dest_servers

    security.declareProtected(ZSYNC_PERMISSION, 'getPath')
    def getPath(self, obj, syncer=None):
        """
        Get a path to obj that the syncer can work with.
        """
        path = obj.getPhysicalPath()
        syncer = self.getZSyncer(syncer)
        path_info = syncer.getPathInfo(path)
        return path_info['relative_path']

    security.declareProtected(ZSYNC_PERMISSION, 'getObjectFromPath')
    def getObjectFromPath(self, path, syncer=None):
        """
        Get a path to obj that the syncer can work with.
        """
        syncer = self.getZSyncer(syncer)
        return syncer._getObject(path)

    # sf bug #1469129: plone calls an action's condition expression before
    # checking its permission expression. So, don't restrict this method
    # too much. "View" is adequate protection, and the action
    # is still protected by its own permission anyway.
    security.declareProtected(Permissions.view, 'isObjectDiffable')
    def isObjectDiffable(self, obj):
        """
        Is the object diffable?
        """
        # Useful for determining whether to show the Diff action.
        base = aq_base(obj)
        syncer = self.getZSyncer()
        if syncer.is_diffable(meta_type=getattr(base, 'portal_type', None)):
            return 1
        if syncer.is_diffable(meta_type=getattr(base, 'meta_type', None)):
            return 1
        return 0

    security.declareProtected(ZSYNC_PERMISSION, 'getZSyncer')
    def getZSyncer(self, name=None):
        """get the specified (or default) zsyncer.
        """
        if name is None or not name.strip():
            name = self._default_zsyncer
        obj = getattr(self, name, None)
        if obj is None:
            raise ValueError, "ZSyncer %s is not found" % name
        return obj

    security.declareProtected(ZSYNC_PERMISSION, 'callManyRemote')
    def callManyRemote(self, methodlist, syncer=None):
        """Call multiple remote methods and return a list of
        return values.

        methodlist should be a sequence of dictionaries with the following
        keys:

          'path': path to the object on which to call the method.
          'method_name': name of the method.
          'args' (optional): list of positional arguments to pass.
          'kwargs' (optional): dictionary of keyword arguments to pass.

        """
        # XXX Other methods could be refactored to use this one.
        syncer = self.getZSyncer(syncer)
        return syncer.callManyRemote(methodlist)

    #######################################################
    # Internal methods
    #######################################################


    def _setDefaults(self, adict):
        # Make sure a status dict has everything the skins need to show it.
        status = adict.get('status', 'Not Found Anywhere!')
        adict.setdefault('status', status)
        adict.setdefault('icon', '')
        adict.setdefault('status_icon',
                         self.getZSyncer().status_icon(status))
        adict.setdefault('status_color',
                         self.getZSyncer().status_colour(status))
        return adict

    def _setActions(self, adict):
        # Add actions to status info.
        # Unfortunately this is impossible to do right:
        # we don't want to include ALL actions,
        # and we have no idea what types may be installed,
        # whether their edit/view links follow reasonable convention,
        # what other actions are 'important', etc.
        # So this is a stupid hack that works OK for at least some
        # some CMFDefault types.
        # XXX this needs better test coverage!
        default =  {'diff': None,
                    'edit': None,
                    'view': None,
                    'sync_status': None,
                    }
        adict['actions'] = default
        try:
            obj = self.getObjectFromPath(adict['relative_path'])
        except ZSyncerObjNotFound:
            return adict
        a_tool = getToolByName(self, 'portal_actions')
        all_actions = a_tool.listFilteredActionsFor(obj)
        actions = all_actions['folder'] + all_actions['object']
        for a in actions:
            if a['id'] == 'zsyncer_diff':
                adict['actions']['diff'] = a
            elif a['id'] in ('zsyncer_obj_status', 'zsyncer_fol_status'):
                adict['actions']['sync_status'] = a
            elif a['name'].lower().strip() == 'view':
                adict['actions']['view'] = a
            elif a['name'].lower().strip() == 'edit':
                adict['actions']['edit'] = a
            else:
                pass #print "Useless action %s" % a['name']
        return adict


def manage_addZSyncerTool(self, id=None, REQUEST=None, 
                          submit=None):
    """add an instance to a folder
    """
    # normally, the defaut id is used.
    if id is None: id = ZSyncerTool.id
    self._setObject(id, ZSyncerTool(id))
    obj = getattr(self, id)
    if REQUEST is not None:
        obj.manage_changeProperties(REQUEST) 
        try: url=self.DestinationURL() 
        except: url=REQUEST['URL1'] 
        url = url + "/manage_main" 
        REQUEST.RESPONSE.redirect(url) 

constructors = (manage_addZSyncerTool,)

InitializeClass(ZSyncerTool)

