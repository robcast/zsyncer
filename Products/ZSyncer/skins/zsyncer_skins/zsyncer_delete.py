##Script (Python) "zsyncer_delete"
##title=Delete one or more objects.
##parameters=came_from, obj_paths, syncer_name=None

"""
Delete one or more objects to all destinations.
"""

from Products.CMFCore.utils import getToolByName
request = context.REQUEST

zs_tool = getToolByName(context, 'portal_zsyncer')
context_path = zs_tool.getPath(context)
if same_type(obj_paths, ''):
    obj_paths = [obj_paths]
messages = zs_tool.doDelete(obj_paths, syncer_name)

# If the delete was successful locally, and the current context was
# one of the deleted objects, we have to change came_from to
# point to the parent, or else we'll end up with a 404.

where_to = context
#print "-------"
if context_path in obj_paths:
    for m in messages:
        if m.status == 200 and str(m).count(context_path):
            where_to = context.aq_inner.aq_parent
            #print "WE HAVE A WINNER"
            break

    #print "---------"

#return printed
request.form['came_from'] = where_to.absolute_url()
#print "HMMM: %s,  %s" % (request.get('came_from'), where_to.absolute_url())
return where_to.zsyncer_result_template(messages=messages)
#return printed
