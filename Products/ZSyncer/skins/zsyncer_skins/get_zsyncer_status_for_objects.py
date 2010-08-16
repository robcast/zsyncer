##Script (Python) "get_zsyncer_status_for_objects"
##title=Get status, given a list of object paths.
##parameters=obj_paths, syncer_name=None

"""
Get status for a list of object paths.
"""

from Products.CMFCore.utils import getToolByName

zs_tool = getToolByName(context, 'portal_zsyncer')
if same_type(obj_paths, ''):
    obj_paths = [obj_paths]
# XXX This is inefficient; syncer should be generalized to compare
# a list of arbitrary paths at once, rather than assuming
# they will always be in the same folder.
# And then comparing subitems of a folder should be implemented
# using that.
statuses = [zs_tool.getStatus(obj_path, syncer_name)[0]
            for obj_path in obj_paths]
return statuses
