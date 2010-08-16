##Script (Python) "object_sync"
##title=Sync one or more objects.
##parameters=obj_paths, syncer_name=None

"""
Sync one or more objects to all destinations.
"""

from Products.CMFCore.utils import getToolByName
#from Products.ZSyncer.utils import StatusMsg

zs_tool = getToolByName(context, 'portal_zsyncer')
if same_type(obj_paths, ''):
    obj_paths = [obj_paths]
messages = zs_tool.doPush(obj_paths, syncer_name)

return context.zsyncer_result_template(messages=messages)
