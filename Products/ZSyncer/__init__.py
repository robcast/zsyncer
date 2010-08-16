# Zope imports.
from Globals import ImageFile
from AccessControl import ModuleSecurityInfo

# Custom imports.
import ZSyncer
from Config import sync_tab_classes
from ConfigUtils import _import, _addSyncTab

# logging
import logging
logger = logging.getLogger('event.ZSyncer')

# Try to import CMF, if so try to import ZSyncerTool, otherwise
# dont bother ;)
try:
    from Products.CMFCore.utils import ToolInit
    CMF = 1
    logger.info('CMF installed, will set up ZSyncerTool')
    from ZSyncerTool import ZSyncerTool
except ImportError:
    CMF = 0
    logger.info('CMF not installed, will not set up ZSyncerTool')


# helps with installation of CMF tool
zs_globals = globals()

def initialize(context): 
    context.registerClass(
            ZSyncer.ZSyncer, 
            constructors = (ZSyncer.manage_addZSyncerForm,
                            ZSyncer.manage_addZSyncer), 
            icon='zsyncer_icon.gif')
    context.registerHelp()
    
    if CMF:
        from Products.CMFCore.DirectoryView import registerDirectory
        registerDirectory('skins', zs_globals)
        from ZSyncerTool import ZSyncerTool
        ToolInit(ZSyncerTool.meta_type, 
                 tools=(ZSyncerTool, ),
                 product_name='ZSyncer',  # NOT meta_type!
                 icon='zsyncer_icon.gif', # Must be in this dir.
                 ).initialize( context )
        # You still have to call the installer external method
        # in the context of your CMF site.

# MONKEY PATCH!
# Add sync tabs to ZMI pages for various Products.
# Oh, for a skinnable ZMI. Some day my zope 3 will come.
# ok rummage through all the items to 
# import, Folder.manage_options is one, but
# if you have custom folderish objects add them to Config.py 

for modpath, classname in sync_tab_classes:
    if classname == 'ZObject':
        isZObject=1
    else:
        isZObject=0
    # do the import...
    try:
        klass = _import(modpath, classname)
        _addSyncTab(klass, isZObject)
    except ImportError:
        logger.info('Failed to add tab to %s, %s; not installed?',
                    modpath, classname)
        continue

misc_ = {}
for icon in ('ok', 'missing', 'extra', 'outdated',):
    misc_['zsyncer_%s.gif' % icon] = ImageFile('www/zsyncer_%s.gif' % icon,
                                               globals())

# Security declarations for useful stuff for skins and UI.
ModuleSecurityInfo('Products.ZSyncer.utils').declarePublic(
    'StatusMsg',
    'listSyncers',
    )


