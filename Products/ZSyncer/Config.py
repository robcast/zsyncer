"""
ZSYNCER CONFIG

In the future we may switch to something like ZConfig.
For now, you should edit this file to configure global
options for your ZSyncers.
"""

# Status name constants.
OOD = 'out of date'
OK = 'ok'
EXTRA = 'extra'
MISSING = 'missing'

# timeout for remote operations, in seconds.
# You may need to increase this if you are likely to sync a
# lot of data at once.
# Currently only applies to ConnectionMgr.
timeout = 120

# syncable:  a list of meta types you can sync by default.
# The management UI allows you to add more.
syncable = [
    'Control_Panel',
    'DTML Method', 
    'DTML Document',
    'Image',
    'File',
    'Page Template',
    'Script (Python)',
    'Z SQL Method',
    'Z Class',
    'Z Object',
    'Folder',
    ]

# sync_tab_classes:
# a list of (modulename, classname) tuples
# which will be patched to add a Sync tab in the ZMI.
# Errors importing any of these will be logged at startup.

sync_tab_classes = [
    ('OFS.Folder', 'Folder'),
    ('App.ApplicationManager', 'ApplicationManager'),
    ('App.Product','Product'),
    ('OFS.OrderedFolder', 'OrderedFolder'),
    ('Products.CMFCore.PortalFolder', 'PortalFolder'),# that does plone too!
    ('ZClasses.ZClass', 'ZObject'),
    #('ZClasses.Method', 'ZClassMethodsSheet'),  # doesn't work.
    ('Products.OrderedFolder.OrderedFolder', 'OrderedFolder'),
    ('Products.BTreeFolder2.BTreeFolder2', 'BTreeFolder2Base'),
    ]

# diffable:
# a list of meta_types for which we can use the diff feature.

diffable = [
    'DTML Method',
    'DTML Document',
    'Page Template',
    'Script (Python)',
    'Document',
    'Text Element',
    'File',
    'Link',
    ]

# diff_methods:
# a list of (meta_type, attribute-name) tuples which tell
# which attribute or method name to use when diffing.

diff_methods = {
    'DEFAULT': 'document_src',  # DTML, ZPT, Python Scripts...
    'Document': 'EditableBody', # CMF & Plone Documents.
    'Text Element': 'value',    # CMFArticle.
    'File': 'data',             # a lot of File objects are plain text.
    'Link': 'getRemoteUrl',     # CMFDefault Link objects. 
    }


# Colors for the UI
color_200 = 'green'
color_error = 'red'

colours = {
    'ok':'#44FF44;',
    'out of date':'orange',
    'missing':'red',
    'extra':'#AA99FF',
    }

icons = {
    'ok': 'misc_/ZSyncer/zsyncer_ok.gif',
    'out of date': 'misc_/ZSyncer/zsyncer_outdated.gif',
    'missing': 'misc_/ZSyncer/zsyncer_missing.gif',
    'extra': 'misc_/ZSyncer/zsyncer_extra.gif',
}

# descriptions:
# Some descriptive text to be used for status reports
# in the UI.
# Some day this may be i18nized... for now you can rewrite them here.

descriptions = {
    'ok':
    'this object is present on both destination and source and is in sync',
    
    'missing':
    'this object is present at the local system but not the remote system; '
    'consider using Put or Delete',
    
    'extra':
    'this object is on the remote system but not the local system; '
    'consider using Get or Delete', 

    'out of date':
    'this object is present on both the remote ' 
    'and local systems, but has been changed locally; '
    'consider using Put',

    'default':
    '(no information available about this status)'
    }

# error_messages:
# descriptions of the possible HTTP response codes we may
# encounter when syncing.

error_messages = {
    '200':
    "Completed with no errors.",

    '403':
    "You are not allowed to do that."
    "You must have the correct account and adequate permissions on the "
    "destination server.",

    '404':
    "Wasn't able to find this object.",

    '500':
    "Server error while syncing."
    }

# reserved_names:
# IDs of objects in the zope app root which may not be synced
# (or even shown in the UI).
# These are taken from Application.py

reserved_names = (
    'standard_html_header',
    'standard_html_footer',
    'standard_error_message',
    # 'Control_Panel',  # ZClasses can't sync if this is reserved.
    'error_log',
    'browser_id_manager',
    'session_data_manager'
    )

# show_tool_actions:
# Whether the ZSyncerTool's actions should be visible by default.
# Only relevant for CMF.
# You should only set this true if you have written some skins,
# we don't currently provide any (planned for 0.7.0).
show_tool_actions = 1


# fudge_secs: the amount of time (in seconds) by which remote
# objects are allowed to be older than local objects before they are
# considered "Out Of Date". This might help you to compensate somewhat
# for incorrect system clocks and reduce the likelihood of false
# "Out of Date" status. The trade-off is that if you set it too high,
# you are more likely to get "OK" status on objects which really are
# "Out Of Date".
fudge_secs = 30


# upload_threshold_kbytes: size above which the server should spool
# uploaded data to a temporary file instead of holding it in RAM.

upload_threshold_kbytes = 512
