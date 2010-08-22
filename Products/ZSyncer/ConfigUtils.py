"""
Utils to help with global configuration of your ZSyncer installation.
"""
import sys, types
from App.special_dtml import DTMLFile
from Products.PageTemplates.PageTemplateFile import PageTemplateFile

import logging
logger = logging.getLogger('event.ZSyncer')

def _import(modpath, classname):
    # techniques swiped from
    # http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/223972
    # First get the module.
    try:
        # maybe we have it already...
        aMod = sys.modules[modpath]
        if not isinstance(aMod, types.ModuleType):
            raise KeyError
    except KeyError:
        # nope, don't have it yet.
        # The last [''] below is very important!
        aMod = __import__(modpath, globals(), locals(), [''])
        sys.modules[modpath] = aMod
    # Got a module, now get the class
    klass = getattr(aMod, classname)
    return klass


def _addSyncTab(klass, isZObject=0):
    """Add a Sync tab in the ZMI for the class named *klass*.
    """
    if isZObject:
        from ZClasses.Method import ZClassMethodsSheet
        ZClassMethodsSheet.sync_html = PageTemplateFile('www/SyncFolder',
                                                        globals())
    else:
        klass.sync_html = PageTemplateFile('www/SyncFolder', globals())
    try:
        manage_options = list(klass.manage_options)
    except TypeError:
        logger.warning('problem with m_o of %s', klass)
        raise
    # Does the manage_options list already have this label?
    # If not, add it.  This is not perfect, since "Sync" is
    # a fairly generic name that somebody else might try to use in
    # the ZMI.
    has_tab = 0
    for opt in manage_options:
        if opt.get('label', '') == 'Sync':
            has_tab = 1
            break
    # Not found, so add the sync tab.
    # There was an old comment here saying "security? that's an issue"
    # but I don't know what exactly that was referring to!
    if not has_tab:
        if isZObject:
            manage_options.append({'label':'Sync',
                      'action':'propertysheets/methods/sync_html'},)
        else:
            manage_options.append({'label':'Sync', 'action':'sync_html'},)
        klass.manage_options = tuple(manage_options)

