"""
Unit and integration tests for ZSyncerTool.

"""

# Standard lib imports.
import os
import sys
import time
import types

# ZopeTestCase imports and setup.
if __name__ == '__main__':
    execfile(os.path.join(sys.path[0], 'framework.py'))
from Testing import ZopeTestCase
from Testing.ZopeTestCase import transaction, user_name, user_password

# CMFTestCase imports.
from Products.CMFTestCase import CMFTestCase

CMFTestCase.installProduct('MailHost')  # CMF barfs without this.
CMFTestCase.installProduct('ZCTextIndex')  # CMF 1.5+ requires this.
CMFTestCase.installProduct('CMFCore')
CMFTestCase.installProduct('CMFDefault')
CMFTestCase.installProduct('ZSyncer')

# Zope imports, must follow the ZopeTestCase product installations.
from Products.CMFCore.utils import getToolByName
from Products.CMFCore.DirectoryView import addDirectoryViews
from Products.CMFDefault.Portal import manage_addCMFSite
from Products.ZSyncer.ZSyncer import manage_addZSyncer
from Products.ZSyncer.ZSyncer import ZSyncerObjNotFound
from Products.ZSyncer import zs_globals
from Products.ZSyncer.ZSyncerTool import manage_addZSyncerTool
from Products.ZSyncer.ZSyncer import ZSyncer, Config, ZSyncerConfigError
from Products.ZSyncer.ZSyncer import OK, EXTRA, MISSING, OOD
from zExceptions import BadRequest

# Common setup before all tests.
# Create the error_log object, must be done before starting the server.
ZopeTestCase.utils.setupSiteErrorLog()
# Start the web server, needed for remote tests.
host, port = ZopeTestCase.utils.startZServer(number_of_threads=4)


class ZSyncerToolSetUp:

    def _makeFolder(self, id, where=None):
        # Create a CMF Folder to play with.
        if where is None:
	    where = self.portal
        where.invokeFactory(type_name='Folder', id=id)
        return getattr(where, id)

    def getPortal(self):
        # Set up a CMF site.
        try:
            manage_addCMFSite(self.app, CMFTestCase.portal_name)
        except BadRequest:
            pass
        return getattr(self.app, CMFTestCase.portal_name)

    def afterSetUp(self):
        #print "afterSetUp being called"
        # Allow the test user to see anything.
        self.setRoles(['Manager', 'Member'])
        # Add a zsyncer tool.
        manage_addZSyncerTool(self.portal)
        self.zs_tool = getToolByName(self.portal, 'portal_zsyncer')
        # Handy to have a reference to its inner zsyncer.
        self.zs = self.zs_tool.getZSyncer()
        # Add a folder to put stuff in.
        self.fol1 = self._makeFolder('folder1')
        # Create a test document.
        data = 'Testing ZSyncer Tool, blah blah blah'
        self.fol1.invokeFactory('Document', 'test_doc1',
                                title='nunya bizness',
                                description='Some boring description',
                                text_format='html',
                                text=data)
        self.fol1.test_doc1.setMetadata({'Subject':
                                         "This is the subject of doc1"})
        self.doc1 = self.fol1.test_doc1
        self.doc1.setSubject(('This is the subject of doc1, so there!',))
        self.doc1.reindexObject() # setSubject does not trigger this.
        self.catalog = self.portal.portal_catalog
        # URL tool is handy.
        self.utool = getToolByName(self.portal, 'portal_url')

    def testSetup(self):
        # This should not give any errors.
        # If it does, fix those first - your tests are not running!
        pass



class TestZSyncerTool(ZSyncerToolSetUp,
                      ZopeTestCase.Sandboxed,
                      CMFTestCase.CMFTestCase,
                      ):

    """Test ZSyncerTool.
    """

    def test_filtered_meta_types(self):
        f_types = self.zs_tool.filtered_meta_types()
        self.assertEqual(len(f_types), 1)
        self.assertEqual(f_types[0]['name'], ZSyncer.meta_type)

    def test_listActions(self):
        # Really stupid whitebox test.
        self.assertEqual(self.zs_tool.listActions(),
                         self.zs_tool._actions)

    def test_initial_state(self):
        # Make sure things look ok after instantiating a ZSyncerTool.
        # It should contain one ZSyncer.
        contents = self.zs_tool.objectItems()
        self.assertEqual(len(contents), 1)
        id, obj = contents[0]
        self.assertEqual(obj.meta_type, ZSyncer.meta_type)
        # The syncer's path should be set.
        self.assertEqual(obj.getSyncerRootPath(),
                         '/'.join(self.portal.getPhysicalPath())
                         )
        self.failUnless(obj.getProperty('use_relative_paths'))


    def test_getStatus(self):
        path = '%s/%s' % (self.fol1.getId(), self.doc1.getId())
        # This explicitly fails when we're not set up yet.
        self.assertRaises(ZSyncerConfigError, self.zs_tool.getStatus, path)

    def test_getDiff(self):
        path = '%s/%s' % (self.fol1.getId(), self.doc1.getId())
        # This explicitly fails when we're not set up yet.
        self.assertRaises(ZSyncerConfigError,
                          self.zs_tool.getDiff, path)

    def test_doPush(self):
        path = '%s/%s' % (self.fol1.getId(), self.doc1.getId())
        # Need a _p_jar in order to sync stuff.
        # Use the subtransaction hack.
        try:
            transaction.commit(1)  # get_ XXX
            # It hasn't been configured yet, so not much happens.
            # We should get empty messages back.
            msgs = self.zs_tool.doPush(path)
            self.assertEqual(msgs, [])
        finally:
            transaction.abort(1)

    def test_callManyRemote(self):
        self.assertEqual(self.zs_tool.callManyRemote([]),
                         [])

    def test_doDelete(self):
        # Make sure the doc is there...
        doc1_id = self.doc1.getId()
        self.failUnless(doc1_id in self.fol1.objectIds())
        # Delete should work locally even without a destination configured.
        path = '%s/%s' % (self.fol1.getId(), self.doc1.getId())
        msgs = self.zs_tool.doDelete([path])
        self.assertEqual(len(msgs), 2)
        # Local message should be OK, remote should show an error.
        self.failUnless(msgs[0].status == 500)
        self.failUnless(msgs[1].status == 200)
        # It should be gone.
        self.failIf(doc1_id in self.fol1.objectIds())

    def test_getDestinations(self):
        # It hasn't been configured yet, so, should be empty.
        self.assertEqual(self.zs_tool.getDestinations(),
                         [])
        # Silly whitebox test, it's a simple wrapper.
        self.zs.destinations = ['http://foo/bar', 'https://bat/baz']
        self.assertEqual(self.zs.dest_servers,
                         self.zs_tool.getDestinations())

    def test_getPath(self):
        path = self.zs_tool.getPath(self.doc1)
        self.assertEqual(path,
                         '/'.join(self.utool.getRelativeContentPath(self.doc1))
                         )

    def test_isObjectDiffable(self):
        self.failUnless(self.zs_tool.isObjectDiffable(self.doc1))
        not_diffable = (self.zs_tool,
                        self.app,
                        self.fol1,
                        self.utool,
                        )
        for nope in not_diffable:
            self.failIf(self.zs_tool.isObjectDiffable(nope))


class ZSToolRemoteSetUp(ZSyncerToolSetUp):

    def afterSetUp(self):
        ZSyncerToolSetUp.afterSetUp(self)
        # Add another folder.
        self.fol2 = self._makeFolder('folder2')
        # Handy to have a direct reference to the first syncer.
        self.zs1 = self.zs_tool.objectValues()[0]
        # Add another zsyncer.
        manage_addZSyncer(self.zs_tool, 'syncer2')
        self.zs2 = self.zs_tool.syncer2
        self.zs2.use_relative_paths = True
        self.zs2.relative_path_base = '/'.join(self.fol2.getPhysicalPath())
        # Point the first syncer at the second one.
        self.zs1.relative_path_base = '/'.join(self.fol1.getPhysicalPath())
        self.zs1.use_relative_paths = True
        self.zs1.dest_servers.append(self.zs2.absolute_url())
        # Let's create a more-or-less identical object in folder2.
        self.fol2.invokeFactory('Document', self.doc1.getId(),
                                title=self.doc1.Title(),
                                description=self.doc1.Description(),
                                text_format='html',
                                text=self.doc1.EditableBody())
        self.doc1_copy = self.fol2[self.doc1.getId()]
        # Let's create an Extra object (only in fol2).
        self.fol2.invokeFactory('Document', 'doc_extra',
                                title=EXTRA,
                                description='Some extra description',
                                text_format='html',
                                text='extra extra read all about it.')
        self.doc_extra = self.fol2.doc_extra
        # Let's create a Missing object (only in fol1).
        self.fol1.invokeFactory('Document', 'doc_missing',
                                title='missing',
                                description='Some missing description',
                                text_format='html',
                                text='missing persons destination unknown')
        self.doc_missing = self.fol1.doc_missing


class TestZSToolRemote(ZSToolRemoteSetUp,
                       ZopeTestCase.Sandboxed,
                       CMFTestCase.CMFTestCase,
                       ):

    """Test interaction with the remote zsyncer.
    """

    def test_doDelete(self):
        # First test deleting an id that is in both folders.
        path = self.doc1.getId()
        id = path
        # Here today...
        self.failUnless(id in self.fol1.objectIds())
        self.failUnless(id in self.fol2.objectIds())
        msgs = self.zs_tool.doDelete(path)
        self.assertEqual(len(msgs), 2)  # One for local, one for remote.
        for m in msgs:
            self.assertEqual(m.status, 200)
        # ... Gone tomorrow.
        self.failIf(id in self.fol1.objectIds())
        self.failIf(id in self.fol2.objectIds())
        # You can also safely use it on a nonexistent id.
        # e.g. the one we just deleted; you just get an error message.
        msgs = self.zs_tool.doDelete(path)
        self.assertEqual(len(msgs), 2)
        for m in msgs:
            self.assertEqual(m.status, 404)
        # You can use it on a 'missing' object; again, you just get 404.
        missing = self.doc_missing.getId()
        self.failUnless(missing in self.fol1.objectIds())
        msgs = self.zs_tool.doDelete(missing)
        self.failIf(missing in self.fol1.objectIds())
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0].status, 404)
        self.assertEqual(msgs[1].status, 200)
        # You can use it on an EXTRA object; again, you just get a 404.
        extra  = self.doc_extra.getId()
        self.failUnless(extra in self.fol2.objectIds())
        msgs = self.zs_tool.doDelete(extra)
        self.failIf(extra in self.fol2.objectIds())
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0].status, 200)
        self.assertEqual(msgs[1].status, 404)

    def test_doPush(self):
        # doPush() requires the "subtransaction hack" to avoid missing
        # _p_ attributes.
        transaction.commit(1)
        try:
            # Try pushing a Missing object, it should no longer be missing.
            missing = self.doc_missing.getId()
            self.failIf(missing in self.fol2.objectIds())
            msgs = self.zs_tool.doPush(missing)
            self.assertEqual(len(msgs), 1)
            self.failIf(msgs[0].status > 200)
            self.failUnless(missing in self.fol2.objectIds())
            # Try pushing an Extra object, this should be not found.
            extra = self.doc_extra.getId()
            self.failIf(extra in self.fol1.objectIds())
            msgs = self.zs_tool.doPush(extra)
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0].status, 404)
        finally:
            transaction.abort(1)

    def test_getDiff(self):
        # Try something that exists in both folders.
        doc_id = self.doc1.getId()
        diff = self.zs_tool.getDiff(doc_id)
        self.failIf(diff['error'])  # empty.
        self.assertEqual(diff['source'], diff['dest'])
        self.failIfEqual(diff['source'], 404)  # Not missing.
        self.failUnless(diff['diff'])  # non-empty.
        # Try an 'extra' object (not found on source.)
        extra = self.doc_extra.getId()
        diff = self.zs_tool.getDiff(extra)
        self.assertEqual(diff['source'], 404)
        self.failIfEqual(diff['dest'], 404)
        self.failIf(diff['diff'])  # empty.
        self.failUnless(diff['error'])  # non-empty.
        # Try a 'missing' object (not found on dest.)
        missing = self.doc_missing.getId()
        diff = self.zs_tool.getDiff(missing)
        self.assertEqual(diff['dest'], 404)
        self.failIfEqual(diff['source'], 404)
        self.failIf(diff['diff'])  # empty.
        self.failUnless(diff['error'])  # non-empty.

    def test_getStatus(self):
        # Try a nonexistent object.
        self.assertRaises(ZSyncerObjNotFound, self.zs_tool.getStatus,
                          'we/have/no/bananas/today')
        # Try a 'missing' object.
        missing = self.doc_missing.getId()
        status, sub_status = self.zs_tool.getStatus(missing)
        self.assertEqual(status['status'], MISSING)
        self.failIf(sub_status)
        # Try an 'extra' object - fails noisily.
        extra = self.doc_extra.getId()
        extra_results = self.zs_tool.getStatus(extra)
        self.assertEqual(extra_results[1], [])
        self.assertEqual(extra_results[0]['status'], EXTRA)
        # Try an id that's in both folders.
        maybe_ok = self.doc1.getId()
        status, sub_status = self.zs_tool.getStatus(maybe_ok)
        self.failIf(sub_status)
        # We're not actually sure what to expect; maybe depends on the
        # time resolution of the platform where we run the tests.
        # Might be OK or out of date.
        self.failUnless(status['status'] in (OK, OOD))
        # Try a whole folder.
        fol = ''
        status, sub_status = self.zs_tool.getStatus(fol)
        self.assertEqual(status['status'], OK)
        for sub in sub_status:
            if sub['id'] == self.doc_extra.getId():
                self.assertEqual(sub['status'], EXTRA)
            elif sub['id'] == self.doc_missing.getId():
                self.assertEqual(sub['status'], MISSING)
            elif sub['id'] == self.doc1.getId():
                self.failUnless(sub['status'] in (OK, OOD))
            else:
                # There should be no others!
                # If you add any in afterSetUp(), will have to update this.
                self.fail()

    def test_callManyRemote(self):
        callMany = self.zs_tool.callManyRemote
        # First try one that doesn't exist.
        bogus = [{'path': 'somepath', 'name': 'somemethod'}]
        self.assertRaises(ZSyncerObjNotFound,
                          callMany, bogus)
        # Now try one method that takes no args.
        real_method1 = {'path': self.zs_tool.getPath(self.doc1),
                        'name': 'getId'}
        self.assertEqual(callMany([real_method1]),
                         [self.doc1.getId()]
                         )
        # Now try two methods at once, with positional and keyword args.
        methods = [
            {'path': self.zs_tool.getPath(self.doc1),
             'name': 'setTitle',
             'args': ['cumulonimbus'],
             },
            {'path': self.zs_tool.getPath(self.doc1),
             'name': 'setDescription',
             'kwargs': {'description': 'very fluffy'}
             }
            ]
        self.assertEqual(callMany(methods), [None, None])
        self.assertEqual(self.doc1_copy.Title(), 'cumulonimbus')
        self.assertEqual(self.doc1_copy.Description(), 'very fluffy')


class TestUI(ZSToolRemoteSetUp,
             CMFTestCase.CMFTestCase,
             ZopeTestCase.FunctionalTestCase,
             ):
    # XXX according to Stefan, the inheritance order should be
    # FunctionalTestCase, CMFTestCase.  But if I do that I get
    # authorization errors when adding the fixture content objects.

    """Test the skin scripts and templates.
    """

    def getPortal(self):
        # Set up a CMF site, AND skins.
        try:
            manage_addCMFSite(self.app, CMFTestCase.portal_name)
        except BadRequest:
            pass
        return getattr(self.app, CMFTestCase.portal_name)

    def afterSetUp(self):
        ZSToolRemoteSetUp.afterSetUp(self)
        self.portal_url = self.portal.absolute_url_path()
        self.basic_auth = '%s:%s' % (user_name, user_password)
        # Need to install the skin.
        skinstool = getToolByName(self.portal, 'portal_skins')
        skinfol_name = 'zsyncer_skins'
        if skinfol_name not in skinstool.objectIds():
            addDirectoryViews(skinstool, 'skins', zs_globals)
        # add our new FSDV to all skinpaths, unless it already exists.
        # I'll just put it at the end.
        skin = 'Basic'
        path = skinstool.getSkinPath(skin)
        path = [s.strip() for s in path.split(',')]
        if skinfol_name not in path:
            path.append(skinfol_name)
            path = ', '.join(path)
            # This will replace the existing skin.
            skinstool.addSkinSelection(skin, path)
        self.portal.changeSkin(skin)

    def test_DiffView(self):
        url = '%s/%s' % (self.doc1.absolute_url_path(), 'zsyncer_diff')
        # Not anonymously viewable by default.
        denied_response = self.publish(url)
        # FOr some reason we don't get 401. To avoid basic auth dialog maybe?
        self.failUnless(denied_response.getStatus() > 200)
        self.failUnless(denied_response.getBody().count('Unauthorized'))
        # Try doc1. Remember, doc1 has a copy in folder2 and that's
        # what we're diffing.
        response = self.publish(url, self.basic_auth)
        self.assertEqual(response.getStatus(), 200)
        self.failUnless(response.getBody().count(self.doc1.EditableBody()))
        new_text = 'OK, now we should get a diff.'
        self.doc1._edit(text=new_text)
        response = self.publish(url, self.basic_auth)
        self.assertEqual(response.getStatus(), 200)
        self.failUnless(response.getBody().count(
            self.doc1_copy.EditableBody()))
        self.failUnless(response.getBody().count(new_text))
        # Try an Extra doc. It's not in zs1's acquisition path,
        # so this barfs; that's OK, the UI should not allow you
        # to make this nonsensical request!
        url = '%s/zsyncer_diff' % (self.doc_extra.absolute_url_path())
        extra_response = self.publish(url, self.basic_auth)
        self.assertEqual(extra_response.getStatus(), 500)
        # Try a Missing doc.
        url = '%s/zsyncer_diff' % (self.doc_missing.absolute_url_path())
        missing_response = self.publish(url, self.basic_auth)
        # The object itself may be missing, but the view is fine.
        self.assertEqual(missing_response.getStatus(), 200)
        self.failUnless(missing_response.getBody().count(MISSING))

    def test_ObjectView(self):
        url = '%s/zsyncer_objectview' % (self.doc1.absolute_url_path())
        # Not anonymously viewable by default.
        denied_response = self.publish(url)
        # For some reason we don't get 401. To avoid basic auth dialog maybe?
        self.failUnless(denied_response.getStatus() > 200)
        self.failUnless(denied_response.getBody().count('Unauthorized'))
        # Compare doc1.
        response = self.publish(url, self.basic_auth)
        self.assertEqual(response.getStatus(), 200)
        # We can't be sure of mod times, it's kinda flaky...
        self.failUnless(response.getBody().count(OK)
                        or response.getBody().count(OOD))
        new_text = 'changing the text.'
        self.doc1._edit(text=new_text)
        response = self.publish(url, self.basic_auth)
        self.assertEqual(response.getStatus(), 200)
        self.failUnless(response.getBody().count(OOD))
        # Try an Extra doc. It's not in zs1's acquisition path,
        # so this barfs on the server; that's OK, the UI should not allow you
        # to make this nonsensical request!
        url = '%s/zsyncer_objectview' % (self.doc_extra.absolute_url_path())
        extra_response = self.publish(url, self.basic_auth)
        self.assertEqual(extra_response.getStatus(), 500)
        # Try a Missing doc.
        url = '%s/zsyncer_objectview' % (self.doc_missing.absolute_url_path())
        missing_response = self.publish(url, self.basic_auth)
        # The object itself may be missing, but the view is fine.
        self.assertEqual(missing_response.getStatus(), 200)
        self.failUnless(missing_response.getBody().count(MISSING))

    def test_FolderView(self):
        url = '%s/zsyncer_folderview' % (self.fol1.absolute_url_path())
        # Not anonymously viewable by default.
        denied_response = self.publish(url)
        # For some reason we don't get 401. To avoid basic auth dialog maybe?
        self.failUnless(denied_response.getStatus() > 200)
        self.failUnless(denied_response.getBody().count('Unauthorized'))
        # Compare the folder.
        response = self.publish(url, self.basic_auth)
        self.assertEqual(response.getStatus(), 200)
        # We can't be sure of mod times, it's kinda flaky...
        self.failUnless(response.getBody().count(OK)
                        or response.getBody().count(OOD))
        # Recursion should basically work.
        url += '?mode=recursive'
        response = self.publish(url, self.basic_auth)
        self.assertEqual(response.getStatus(), 200)
        # XXX So much going on in the view it's hard to say what to test...
        # this could use more fleshing out, and maybe some use-case-driven
        # test cases, e.g. one test follows several links.

    def test_Delete(self):
        # Try a doc in both folders.
        self.failUnless(self.doc1.getId() in self.fol1.objectIds())
        self.failUnless(self.doc1.getId() in self.fol2.objectIds())
        def make_url(synctool, obj):
            url = '%s/zsyncer_delete?came_from=%s&obj_paths=%s' % (
                obj.absolute_url_path(),
                synctool.getPath(obj),
                synctool.getPath(obj),
                )
            return url
        url = make_url(self.zs_tool, self.doc1)
        # First, try without auth:
        denied_response = self.publish(url)
        # Unauthorized causes a redirect.
        self.failUnless(denied_response.getStatus() == 302)
        self.failUnless(denied_response.getBody().count('Unauthorized'))
        # Now try with auth.
        del_response = self.publish(url, self.basic_auth)
        self.assertEqual(del_response.getStatus(), 200)
        self.failIf(self.doc1.getId() in self.fol1.objectIds())
        self.failIf(self.doc1.getId() in self.fol2.objectIds())
        # Try an Extra doc.
        self.failIf(self.doc_extra.getId() in self.fol1.objectIds())
        self.failUnless(self.doc_extra.getId() in self.fol2.objectIds())
        url = make_url(self.zs_tool, self.doc_extra)
        extra_response = self.publish(url, self.basic_auth)
        self.assertEqual(extra_response.getStatus(), 200)
        # It's remotely deleted.
        self.failIf(self.doc_extra.getId() in self.fol2.objectIds())
        # Try a Missing doc.
        self.failUnless(self.doc_missing.getId() in self.fol1.objectIds())
        self.failIf(self.doc_missing.getId() in self.fol2.objectIds())
        url = make_url(self.zs_tool, self.doc_missing)
        missing_response = self.publish(url, self.basic_auth)
        self.assertEqual(missing_response.getStatus(), 200)
        # It's locally deleted.
        self.failIf(self.doc_missing.getId() in self.fol1.objectIds())


class ZZZTestCleanUp(ZopeTestCase.ZopeTestCase):

    def test_WasCleanedUp(self):
        # Many Zope products have tests that obnoxiously pollute
        # the ZODB for subsequent tests.
        # This is driving me nuts so let's make sure that we
        # don't contribute to the problem!
        self.failIf(CMFTestCase.portal_name in self.app.objectIds())
        # Could add other things if there are any.
        # Is the error_log a problem?


def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestZSyncerTool))
    suite.addTest(makeSuite(TestZSToolRemote))
    suite.addTest(makeSuite(TestUI))
    suite.addTest(makeSuite(ZZZTestCleanUp))
    return suite

if __name__ == '__main__':
    framework()
