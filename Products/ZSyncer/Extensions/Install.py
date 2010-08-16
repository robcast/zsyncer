"""\

This file is an installation script for this tool.
To use, either:

use the PortalQuickInstaller tool if you have it installed
(it comes with plone 2.0),

- or -

install by hand as follows:

Add an external method to the root of the CMF Site that you want the
tool registered in with the configuration:

 id: install_events
 title: Install ZSyncer Tool *optional*
 module name: ZSyncer.Install
 function name: install

Then go to the management screen for the newly added external method
and click the 'Try it' tab.  The install function will execute and give
information about the steps it took to register and install the
tool into your CMF Site instance.
You may then delete the external method.

"""

from Products.CMFCore.DirectoryView import addDirectoryViews
from Products.CMFCore.utils import getToolByName
from Products.ZSyncer import ZSyncerTool, zs_globals 
from cStringIO import StringIO

def install(self):
    " Register the ZSyncerTool with portal_types and friends "
    out = StringIO()
    skinstool = getToolByName(self, 'portal_skins')
    urltool = getToolByName(self, 'portal_url')
    actionstool = getToolByName(self, 'portal_actions')
 
    # Add the ZSyncerTool tool to the site's root
    p = urltool.getPortalObject()
    tool_id = ZSyncerTool.id
    if not tool_id in p.objectIds():
        p.manage_addProduct['ZSyncer'].manage_addTool(
            type=ZSyncerTool.meta_type)
        out.write("Added %s tool\n" % tool_id)
    else:
        out.write("Already have %s tool, skipping\n" % tool_id)
    
    # Register Filesystem Directory View for our skins.
    skinfol_name = 'zsyncer_skins'
    if skinfol_name not in skinstool.objectIds():
        # add Filesystem Directory Views for any sub-directories
        # in our skin/ directory.  These directories should already be
        # configured.  skin/ itself is NOT used for an FSDV.
        addDirectoryViews(skinstool, 'skins', zs_globals)
        out.write("Added %s directory view to portal_skins\n" % skinfol_name)

    # add our new FSDV to all skinpaths, unless it already exists.
    # I'll just put it at the end.
    skins = skinstool.getSkinSelections()
    for skin in skins:
        path = skinstool.getSkinPath(skin)
        path = [s.strip() for s in path.split(',')]
        if skinfol_name not in path:
            path.append(skinfol_name)
            path = ', '.join(path)
            # addSkinSelection will replace existing skins as well.
            skinstool.addSkinSelection(skin, path)
            out.write("Added %s to %s skin\n" % (skinfol_name, skin))
        else:
            out.write("Skipping %s skin, %s is already set up\n" % (skin,
                skinfol_name))

    # Register as an Action Provider
    tool_id = ZSyncerTool.id
    if tool_id in actionstool.listActionProviders():
        out.write("%s is already registered as an action provider.\n" %
                  tool_id)
    else:
        actionstool.addActionProvider(tool_id) 
        out.write("Registered %s as a new action provider.\n" % tool_id)
       
    
    return out.getvalue()

