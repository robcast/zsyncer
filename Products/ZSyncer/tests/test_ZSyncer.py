"""
Unit and integration tests for ZSyncer.

We currently test a lot of non-API methods because there are
so many of them, and we really want to be sure the implementation works!
This is largely to get a good sense of the current behavior of the code
to enable future cleanup and refactorings.
"""

# Standard lib imports.
import base64
import cStringIO
import os
import sys
import time
import types

# ZopeTestCase imports and setup.
if __name__ == '__main__':
    execfile(os.path.join(sys.path[0], 'framework.py'))
from Testing import ZopeTestCase
from Testing.ZopeTestCase import transaction, user_name, user_password
ZopeTestCase.installProduct('ZSyncer')

# Zope imports, must follow the ZopeTestCase stuff.
from AccessControl import Unauthorized, getSecurityManager
from DateTime import DateTime
from OFS.Traversable import NotFound
from Products.ZSyncer.ZSyncer import manage_addZSyncer
from Products.ZSyncer.utils import ZSyncerObjNotFound, ZSyncerConfigError
from Products.ZSyncer import Config, ZSyncer, utils
from zExceptions import BadRequest


## standard_permissions = ZopeTestCase.standard_permissions
## access_permissions   = ['View management screens']
## change_permissions   = ['Change Python Scripts']
## all_permissions      = standard_permissions + access_permissions + \
##                        change_permissions

# Create the error_log object, must be done before starting the server.
ZopeTestCase.utils.setupSiteErrorLog()
# Start the web server, needed for remote tests.
host, port = ZopeTestCase.utils.startZServer(number_of_threads=4)

def _makeFile(id, title='', text='', container=None ):
    # Helper for setup: make an object to play with.
    if container is None:
        raise ValueError, "No container specified"
    container.manage_addProduct['OFSP'].manage_addFile(
        id=id, title=title, file=text, content_type='text/plain')
    return getattr(container, id)


# Mock objects for some tests.
class FakeResponse:
    def __init__(self):
        self.output = []
    def write(self, data):
        self.output.append(data)
    def flush(self):
        pass
    def read(self):
        return ''.join(self.output)

class DummyMessage:
    def __init__(self, text):
        self.msg = text
    def html(self):
        return self.msg

class ZSyncerSetUp:

    def afterSetUp(self):
        # Allow the test user to see and do anything.
        self.setRoles(['Manager', 'Member'])
        # Add a zsyncer.
        manage_addZSyncer(self.folder, 'zs1')
        self.zs1 = self.folder.zs1
        id = 'some_file'
        text = 'This is a test file. It has some text in it.'
        title = 'A file for testing'
        afile = _makeFile(id=id, text=text,
                          title=title,
                          container=self.folder)
        self.file1 = self.folder[id]
        self.file1_id = id
        self.file1_text = text
        self.file1_title = title
        self.file1_path = '/'.join(self.file1.getPhysicalPath())

    def test_setUp(self):
        # This should not give any errors.
        # If it does, fix those first - your tests are not running!
        pass


class TestZSyncerBasics(ZSyncerSetUp, ZopeTestCase.ZopeTestCase):

    """Test everything that does NOT require a remote connection.
    """

    def test_manage_getSource(self):
        self.assertEqual(self.zs1.manage_getSource(self.file1_id),
                         self.file1_text)
        # If we remove the file, we get 404.
        self.folder.manage_delObjects(self.file1_id)
        self.assertEqual(self.zs1.manage_getSource(self.file1_id),
                         404)

    def test_status_colour(self):
        sc = self.zs1.status_colour
        # Whitebox test: compare to values from the config file.
        expected = Config.colours
        self.assertEqual(sc(ZSyncer.OK), expected[ZSyncer.OK])
        self.assertEqual(sc(ZSyncer.MISSING), expected[ZSyncer.MISSING])
        self.assertEqual(sc(ZSyncer.OOD), expected[ZSyncer.OOD])
        self.assertEqual(sc(ZSyncer.EXTRA), expected[ZSyncer.EXTRA])
        self.assertEqual(sc('asdfafuasf', default='a can of spam'),
                         'a can of spam')

    def test_status_descr(self):
        # I don't really care about much except that it's a string.
        for status in (ZSyncer.OK, ZSyncer.MISSING, 'an imaginary status'):
            descr = self.zs1.status_descr(status)
            self.assertEqual(type(descr), type(''))

    def test_status_icon(self):
        status_icon = self.zs1.status_icon
        expected = {ZSyncer.OK: '/misc_/ZSyncer/zsyncer_ok.gif',
                    ZSyncer.MISSING: '/misc_/ZSyncer/zsyncer_missing.gif',
                    ZSyncer.OOD: '/misc_/ZSyncer/zsyncer_outdated.gif',
                    ZSyncer.EXTRA: '/misc_/ZSyncer/zsyncer_extra.gif',
                    'an imaginary status': '',
                    }
        for status in expected.keys():
            self.assertEqual(expected[status],
                             status_icon(status)
                             )

    def test_isComparisonAllowed(self):
        zs1 = self.zs1
        file1 = self.file1
        self.failUnless(zs1._isComparisonAllowed(file1))
        # Now let's try some things that should restrict it.
        zs1.filterObjects = 1
        zs1.syncable = []
        self.failIf(zs1._isComparisonAllowed(file1))
        # add the meta type and we should be ZSyncer.OK.
        zs1.syncable.append(file1.meta_type)
        self.failUnless(zs1._isComparisonAllowed(file1))
        # Now, explicitly filter it out.
        zs1.filterOutObjects = 1
        zs1.non_syncable.append(file1.meta_type)
        self.failIf(zs1._isComparisonAllowed(file1))
        # Turn off filtering and we should be OK again.
        zs1.filterOutObjects = 0
        self.failUnless(zs1._isComparisonAllowed(file1))
        # Now, pretend it's a broken object.
        file1.meta_type = 'Broken Because something horrible happened.'
        self.failIf(zs1._isComparisonAllowed(file1))

    def test_getInfoForObject(self):
        obj = self.file1
        d = self.zs1._getInfoForObject(obj)
        self.assertEqual(d['id'], self.file1_id)
        # Note, comparing a DateTime to a supposedly-identical DateTime
        # apparently occasionally fails due to some precision issue.
        self.assertEqual(d['last_modified_time'].ISO(),
                         obj.bobobase_modification_time().ISO())
        self.assertEqual(d['dc_modtime'], '')
        self.assertEqual(d['icon'], '/' + obj.icon)
        self.assertEqual(d['path'], obj.getPhysicalPath()[-1:])
        self.assertEqual(d['meta_type'], 'File')
        self.assertEqual(d['is_folder'], 0)

    def test_getPathInfo(self):
        path = self.file1.absolute_url_path()
        path_info = self.zs1.getPathInfo(path)
        self.assertEqual(path_info['absolute_url_path'],
                         self.file1.absolute_url_path())
        self.assertEqual(path_info['relative_path'],
                         self.file1_id)
        self.assertEqual(path_info['id_or_path'],
                         self.file1_id)
        # Tuple argument should be OK too.
        path_info_2 = self.zs1.getPathInfo(self.file1.getPhysicalPath())
        self.assertEqual(path_info, path_info_2)
        # A non-existent object should give back the original path.
        bad_path = "/I/do/not/exist"
        bad_info = self.zs1.getPathInfo(bad_path)
        self.assertEqual(bad_info['relative_path'], bad_path)
        self.assertEqual(bad_info['absolute_url_path'], bad_path)
        self.assertEqual(bad_info['id_or_path'], 'exist')

    def test_getSyncerRoot(self):
        zs1 = self.zs1
        path = self.folder.absolute_url_path()
        # Try it in relative mode.
        zs1.use_relative_paths = 1
        zs1.relative_path_base = path
        obj = zs1._getSyncerRoot()
        self.assertEqual(obj, self.folder)
        zs1.relative_path_base = ''
        # That tells zs1 to use its parent, which works out the same.
        self.assertEqual(obj, self.folder)
        # Try it in non-relative mode.
        zs1.use_relative_paths = 0
        obj = zs1._getSyncerRoot()
        self.assertEqual(obj, self.app)

    def test_getSyncerRootId(self):
        obj = self.zs1._getSyncerRoot()
        self.assertEqual(self.zs1.getSyncerRootId(),
                         obj.getId())
        
    def test_getSyncerRootPath(self):
        zs1 = self.zs1
        gsrp = zs1.getSyncerRootPath
        zs1.use_relative_paths = 0
        self.assertEqual(gsrp(), '/')
        zs1.use_relative_paths = 1
        self.assertEqual(gsrp(), '')
        zs1.relative_path_base = 'foo/bar/baz'
        self.assertEqual(gsrp(), 'foo/bar/baz')
        # Ensure that whitespace is stripped.
        zs1.relative_path_base = '  foo/bar/baz '
        self.assertEqual(gsrp(), 'foo/bar/baz')

    def test_traverseFromRoot(self):
        path = self.file1.getId()
        obj = self.zs1.traverseFromRoot(path)
        self.assertEqual(self.file1, obj)
        bad_path = "/I/do/not/think/therefore/I/am/not"
        self.assertRaises(ZSyncerObjNotFound, self.zs1.traverseFromRoot,
                          bad_path)

    def test_getRelativePhysicalPath(self):
        zs1 = self.zs1
        grpp = zs1._getRelativePhysicalPath
        self.assertRaises(ZSyncerObjNotFound, grpp, 'no/such/thing')
        # Test w/ 'strict' argument (default) and relative paths.
        zs1.use_relative_paths = True
        zs1.relative_path_base = '/'.join(self.folder.getPhysicalPath())
        file_outside_fol = _makeFile(id='foofile', text='who cares?',
                                     container=self.app)
        self.assertRaises(ValueError, grpp, file_outside_fol, strict=True)
        # Should be same w/ default values.
        self.assertRaises(ValueError, grpp, file_outside_fol)
        # Test w/ false 'strict' argument.
        # No error if using relative paths but no 'strict'.
        # But the output is undefined.
        grpp(file_outside_fol, strict=False)
        # Now try without use_relative_paths.
        zs1.use_relative_paths = False
        self.assertEqual(('', 'foofile'),
                         grpp(file_outside_fol))
        # Should get predictable results and no error if path includes
        # the object, even in strict mode.
        zs1.use_relative_paths = True
        zs1.relative_path_base = '/'
        self.assertEqual(('', 'foofile'),
                         grpp(file_outside_fol))

        # OK, now test relative results for an object that is in the
        # same folder as the syncer.
        zs1.relative_path_base = ''
        zs1.use_relative_paths = True
        self.assertEqual(grpp(self.file1),
                         (self.file1.getId(),)
                         )
        # Test relative results of providing absolute path.
        self.assertEqual(grpp(self.file1_path),
                         (self.file1.getId(),)
                         )

    def test_callMethod_(self):
        caller = self.zs1.callMethod_
        path = ''  # This should resolve to our syncer root itself.
        self.assertEqual(caller(path, 'objectIds', spec='File'),
                         [self.file1_id]
                         )
        self.assertEqual(caller(path, 'getId'),
                         self.folder.getId())

        # Test security!
        # Create a folder with restricted permissions...
        self.folder.manage_addFolder('folder2')
        self.folder.folder2.manage_permission('Access contents information',
                                              roles=[])
        # First verify that it's restricted...
        self.assertRaises(Unauthorized,
                          self.folder.restrictedTraverse, 'folder2'
                          )
        # ... Now verify that ZSyncer doesn't give its users a back door
        # to call the restricted method.
        self.assertRaises(Unauthorized,
                          caller, self.folder.folder2.getId(), 'objectIds')
        # Passing None as the path should give us the remote syncer.
        self.assertEqual(caller(None, 'getId'),  self.zs1.getId())

    def test_callMethods_(self):
        caller = self.zs1.callMethods_
        path = ''  # This should resolve to our syncer root itself.
        methodlist = [{'path': path, 'name': 'objectIds',
                       'kwargs': {'spec': 'File'},
                       },
                      {'path': path, 'name': 'getId'},
                      ]
        self.assertEqual(caller(methodlist),
                         [[self.file1_id,],
                          self.folder.getId()]
                         )
        # Test security!
        # Create a folder with restricted permissions...
        self.folder.manage_addFolder('folder2')
        self.folder.folder2.manage_permission('Access contents information',
                                              roles=[])
        # First verify that it's restricted...
        self.assertRaises(Unauthorized,
                          self.folder.restrictedTraverse, 'folder2'
                          )
        # ... Now verify that ZSyncer doesn't give its users a back door
        # to call the restricted method.
        self.assertRaises(Unauthorized,
                          caller, [{'path': self.folder.folder2.getId(),
                                    'name': 'objectIds'}]
                          )
        # Passing no path should give the syncer itself.
        self.assertEqual(caller([{'name': 'getId'}]),
                         [self.zs1.getId()])
        # Same for passing None.
        self.assertEqual(caller([{'name': 'getId', 'path': None}]),
                         [self.zs1.getId()])


    def test_getObject(self):
        zs1 = self.zs1
        path = self.file1.absolute_url_path()
        self.assertEqual(zs1._getObject(path),
                         self.file1)
        path = self.file1.getId()
        self.assertEqual(zs1._getObject(path),
                         self.file1)
        # Try a nonexistent object.
        self.assertRaises(ZSyncerObjNotFound,
                          zs1._getObject, 'this path is bogus')


    def test_manage_replaceObject(self):
        path = (self.file1_id,)
        # Make sure the object is actually there...
        self.failUnless(self.file1 in self.folder.objectValues())
        # Calling w/ an invalid path should return 404 and have no effect.
        status = self.zs1.manage_replaceObject(path + ('nowhere',))
        self.assertEqual(status, 404)
        self.failUnless(self.file1 in self.folder.objectValues())
        # We're going to delete file1, so get an export of it first...
        # use the subtransaction hack to get a _p_oid and _p_jar.
        exp_data = cStringIO.StringIO()
        try:
            transaction.commit(1)
            self.file1._p_jar.exportFile(self.file1._p_oid, exp_data)
        finally:
            transaction.abort(1)
        exp_data = exp_data.getvalue()
        # Calling w/ the correct path and None should remove the file.
        status = self.zs1.manage_replaceObject(path, None)
        self.failIf(self.file1 in self.folder.objectValues())
        self.assertEqual(status, 200)
        # Now try again with some pickled data.
        status = self.zs1.manage_replaceObject(path, exp_data)
        self.failUnless(self.file1_id in self.folder.objectIds())
        self.assertEqual(status, 200)

        # Try with a file larger than the config threshold and
        # make sure it still works.
        Config.upload_threshold_kbytes = 0
        self.folder.manage_delObjects(self.file1_id)
        status = self.zs1.manage_replaceObject(path, exp_data)
        self.failUnless(self.file1_id in self.folder.objectIds())
        self.assertEqual(status, 200)
        # ... and set it back, now we'll use stringIO for remaining tests.
        Config.upload_threshold_kbytes = sys.maxint
        # Try within a subfolder - had some security problems with this...
        self.folder.manage_addFolder('folder2')
        new_path = ('folder2', self.file1_id)
        try:
            # sigh... the new folder needs a _p_jar too.
            transaction.commit(1)
            new_status = self.zs1.manage_replaceObject(new_path, exp_data)
            self.assertEqual(new_status, 200)
        finally:
            transaction.abort(1)

        # XXX try with OrderFolder and verify that order is preserved.
        # XXX try with something that has a DAV lock and ensure that
        # it's cleared.


    def test_manage_listObjects(self):
        zs1 = self.zs1
        path = self.folder.absolute_url_path()
        all = zs1.manage_listObjects(path)
        self.assertEqual(len(all), 2)
        # Check the first item: it should represent the compared object.
        self.assertEqual(all[0]['id'],
                         self.folder.getId())
        # Now check sub-objects.
        sub_items = all[1].items()
        self.failUnless(len(sub_items))
        for key, value in sub_items:
            self.failUnless(key in self.folder.objectIds())
            self.assertEqual(value['id'], key)
            self.assertEqual(value['icon'], '/' + self.folder[key].icon)
        # Now try the 'do_base' argument.
        nobase = zs1.manage_listObjects(path, do_base=0)
        self.assertEqual({}, nobase[0])
        # The sub-items should be the same.
        # XXX but I can't just compare them because the mod times
        # compare a few milliseconds off!!
        #self.assertEqual(all[1],  nobase[1])

    def test_is_diffable(self):
        # It depends mostly on what's in Config.
        # Since we're monkeying with a module, we have to
        # be sure to restore it after we're done or we might break
        # other tests that depend on it.
        old_diffable = Config.diffable
        try:
            Config.diffable = []
            self.failIf(self.zs1.is_diffable('foo_type'))
            Config.diffable = ['foo_type']
            self.failUnless(self.zs1.is_diffable('foo_type'))
            self.failUnless(self.zs1.is_diffable('foo_type', ZSyncer.OK))
            self.failUnless(self.zs1.is_diffable('foo_type', ZSyncer.OOD))
            self.failIf(self.zs1.is_diffable('foo_type', ZSyncer.MISSING))
            self.failIf(self.zs1.is_diffable('foo_type', ZSyncer.EXTRA))
        finally:
            Config.diffable = old_diffable


    def test_getErrorAdvice(self):
        # Just make sure it's a list of strings.
        zs1 = self.zs1
        error_type, error_value = 'ImaginaryError', 'something bad happened.'
        msg = zs1.getErrorAdvice(error_type, error_value)
        self.failUnless(len(msg) > 0)
        self.failUnless(isinstance(msg, type([])))
        for text in msg:
            self.failUnless(isinstance(text, type('')))

    def test_get_status(self):
        gs = self.zs1._get_status
        # Need at least one non-None and non-empty argument.
        self.assertRaises(ValueError, gs, {}, {})
        self.assertRaises(ValueError, gs, None, None)
        # If only the source item, result is MISSING.
        # Also since we provide no timestamps, the calculated ones
        # come back as empty string.
        status, item = gs({'foo': 'bar'}, {})
        self.assertEqual(status, item['status'], ZSyncer.MISSING)
        self.assertEqual('',
                         item['src_best_modtime'], item['dest_best_modtime']
                         )
        # If only the dest item, result is ZSyncer.EXTRA.
        status, item = gs({}, {'bat': 'baz'})
        self.assertEqual(status, item['status'], ZSyncer.EXTRA)
        self.assertEqual('',
                         item['src_best_modtime'], item['dest_best_modtime']
                         )
        # OK, let's manufacture some dicts with some more interesting
        # info.
        time1 = DateTime('August 10, 2005')
        time2 = DateTime('August 11, 2005')
        # First, try them equal.
        src = {'last_modified_time': time1}
        dest = {'last_modified_time': time1}
        status, item = gs(src, dest)
        self.assertEqual(status, item['status'], ZSyncer.OK)
        self.assertEqual(time1, item['dest_mod_time'], item['src_mod_time'])
        # Now try with dest older than src.
        src = {'last_modified_time': time2}
        dest = {'last_modified_time': time1}
        status, item = gs(src, dest)
        self.assertEqual(status, item['status'], ZSyncer.OK)
        self.assertEqual(time1, item['dest_mod_time'])
        self.assertEqual(time2, item['src_mod_time'])
        # Now try with dest younger than src.
        src = {'last_modified_time': time1}
        dest = {'last_modified_time': time2}
        status, item = gs(src, dest)
        self.assertEqual(status, item['status'], ZSyncer.OOD)
        self.assertEqual(time2, item['dest_mod_time'])
        self.assertEqual(time1, item['src_mod_time'])

    def test_isReserved(self):
        """stuff to prevent syncing in the zope root.
        """
        zs1 = self.zs1
        self.failUnless(zs1._isReserved(zs1))
        self.failIf(zs1._isReserved(self.folder))
        old_reserved = Config.reserved_names
        try:
            Config.reserved_names = (self.folder.getId(),)
            self.failUnless(zs1._isReserved(self.folder))
        finally:
            # Be sure to clean this up or other tests break.
            Config.reserved_names = old_reserved

    def test_getExportData(self):
        ged = self.zs1.manage_getExportData
        path = self.file1.getId()
        # We need the object to have an OID.
        # Use the stupid subtransaction trick to make that happen.
        try:
            transaction.commit(1)
            data = ged(path)
            expected = self.folder.manage_exportObject(self.file1.getId(),
                                                      download=1)
            self.assertEqual(data, expected)
        finally:
            transaction.abort(1)

    def test_call_(self):
        from cPickle import dumps, loads
        zs1 = self.zs1
        def call_wrapper(id, args, kwargs):
            # Make it easier to set up and test.
            arg = dumps((id, args, kwargs))
            result = zs1.call_(arg)
            return loads(result)

        success, result = call_wrapper('getId', (), {})
        self.failUnless(success)
        self.assertEqual(result, zs1.getId())
        # Try with a nonexistent method.
        success, result = call_wrapper('no_such_method', (), {})
        self.failIf(success)

    def test_touch(self):
        # Find an object and check its timestamp.
        path = self.zs1._getRelativePhysicalPath(self.file1)
        old_t = self.file1.bobobase_modification_time()
        time.sleep(1)
        # Touch and check its timestamp again, should be greater.
        self.zs1.touch(path)
        self.failUnless(self.file1.bobobase_modification_time() > old_t)
        # The timestamp arg is checked for validity.
        self.assertRaises(AssertionError, self.zs1.touch, path,
                          'not a date')
        # Try passing valid timestamp.
        # In order for this to work, the obj must have a modification_date
        # attribute.
        self.file1.modification_date = self.file1.bobobase_modification_time()
        other_date = DateTime('1/31/2005 8:24 AM')
        self.zs1.touch(path, other_date)
        self.assertEqual(other_date, self.file1.modification_date)

    def test_getFirstDestination(self):
        self.assertRaises(ZSyncerConfigError, self.zs1._getFirstDestination)
        self.zs1.dest_servers.append('blah')
        self.assertEqual('blah', self.zs1._getFirstDestination())

    def test_get_time(self):
        # It returns a string.
        t = self.zs1._get_time()
        self.failUnless(type(t) is types.StringType)
        # XXX this is a stub test, flesh it out!

    def test_log(self):
        fpath = os.path.join(os.getcwd(), 'test_log_output')
        try:
            self.zs1.logfile = fpath
            messages = ['yes', 'we', 'have', 'no', 'cheese']
            now = self.zs1._get_time()
            #import pdb; pdb.set_trace()
            self.zs1._log(messages)
            logfile = open(fpath, 'r')
            data = logfile.readlines()
            logfile.close()
            self.assertEqual(len(data), 1)
            # XXX slow system can break the next test!!!
            self.failUnless(data[0].startswith(now))
            for expected_text in messages:
                self.failUnless(data[0].count(expected_text))
            # Make sure that further logging appends.
            another = 'yet another message'
            self.zs1._log(another)
            logfile = open(fpath, 'r')
            data = logfile.readlines()
            logfile.close()
            self.assertEqual(len(data), 2)
            self.failUnless(data[1].startswith(now))
            self.failUnless(data[1].count(another))
        finally:
            try:
                os.unlink(fpath)
            except:
                pass

    def test_do_one_msg(self):
        request = FakeResponse()  # Just a place to stuff the response.
        request.RESPONSE = FakeResponse()
        s = DummyMessage('hellooooo')
        self.zs1._do_one_msg(s, request)
        self.assertEqual(request.RESPONSE.read(), s.html())
        s2 = DummyMessage(' again')
        self.zs1._do_one_msg(s2, request)
        self.assertEqual(request.RESPONSE.read(), s.html() + s2.html())
        self.assertEqual(self.zs1._do_one_msg('plain str not OK'),
                         0)

    def test_do_messages(self):
        phrases = ('hi', 'there')
        msgs = self.zs1._do_messages(phrases)
        self.assertEqual(len(msgs), len(phrases))
        for orig, msg in zip(phrases, msgs):
            self.failUnless(msg.html().count(orig))
            self.assertEqual(msg.status, 200)
        # Bugfix for 0.7.1:
        # Ensure that if I pass TextMsg instances, they come through
        # unchanged.
        msgs = [utils.TextMsg('test1'), utils.StatusMsg('test2', 500)]
        output = self.zs1._do_messages(msgs)
        self.assertEqual(msgs, output)

class TestUtils(ZopeTestCase.ZopeTestCase):

    # These have pretty minimal dependencies, don't need the
    # rest of ZSyncer.

    def test_lstrip(self):
        self.assertEqual(utils.lstrip('  blah'), 'blah')
        self.assertEqual(utils.lstrip('abcde', 'a'), 'bcde')
        self.assertEqual(utils.lstrip('aaaabcde', 'a'), 'bcde')
        # Regression test: it used to spin forever on empty strings.
        self.assertEqual(utils.lstrip('', ''), '')

    def test_isZClassFolder(self):
        self.failIf(utils.isZClassFolder(self.folder))
        afile = _makeFile(id='afile', container=self.folder)
        self.failIf(utils.isZClassFolder(self.folder.afile))
        # XXX We should make a ZClassFolder and test that!!

    def test_normalizeRelativeURL(self):
        norm = utils.normalizeRelativeURL
        self.assertRaises(TypeError, norm, None)
        self.assertEqual(norm('/'), '/')
        self.assertEqual(norm('a/b/c'), 'a/b/c')
        self.assertEqual(norm('a//b/c'), 'a/b/c')
        self.assertEqual(norm('a/../b/c'), 'b/c')
        self.assertEqual(norm('a/..'), '')
        self.assertEqual(norm('a/../b'), 'b')
        self.assertEqual(norm('a/b/../..'), '')
        self.assertEqual(norm('a/b/c/../../../../..'), '')

    def test_normalize_time(self):
        now = DateTime()
        current_year = now.year()
        self.failUnless(isinstance(utils.normalize_time(now),
                                   types.StringType))
        # It should not contain the year.
        self.failIf(utils.normalize_time(now).count(str(current_year)))
        # An old date should contain the year.
        last_year = current_year - 1
        date_str = '01/01/%d 12:30 pm' % last_year
        old_date = DateTime(date_str)
        utils.normalize_time(old_date)
        self.failUnless(utils.normalize_time(old_date).endswith(str(last_year)
                                                                ))
        self.failUnless(utils.normalize_time(old_date).startswith('Jan 01'))
        # It should not contain the time.
        self.failIf(utils.normalize_time(old_date).count('12:30'))
        # We can also pass a string and get same results.
        self.assertEqual(utils.normalize_time(old_date),
                         utils.normalize_time(date_str))
        # Bad date should return empty string.
        self.assertEqual('', utils.normalize_time(''))
        self.assertEqual('', utils.normalize_time('abcd 99'))

    def test_listSyncers(self):
        # Starts empty...
        self.assertEqual([], utils.listSyncers(self.app))
        # ... then if we add syncers, we see them.
        manage_addZSyncer(self.app, 'zs1')
        zs1 = self.app.zs1
        results = utils.listSyncers(self.app)
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result['syncer'], zs1)
        self.failUnless(result['url'].startswith(zs1.absolute_url()))
        # XXX should test when we have a ZSyncerTool too, but
        # that probably doesn't belong here due to dependencies.
        # Could make a mock ZSyncerTool I guess.

    def test_listSyncers_bug_1325930(self):
        # Regression test for Bug 1325930 (sourceforge):
        # If the syncer is not in the root, the folder argument
        # should be relative to the syncer's base path.
        manage_addZSyncer(self.folder, 'zs2')
        zs2 = self.folder.zs2
        zs2.manage_changeProperties(
            use_relative_paths=1,
            relative_path_base=self.folder.absolute_url_path()
            )
        results = utils.listSyncers(self.folder)
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result['syncer'], zs2)
        self.failUnless(result['url'].endswith(
            '?folder=%s' % '/'.join(zs2._getRelativePhysicalPath(self.folder)
                                    )))
        # If the syncer's base path is such that you can't sync here,
        # it doesn't show up at all.
        results = utils.listSyncers(self.app)
        self.failIf(results)


class RemoteSetUp:
    def afterSetUp(self):
        ZSyncerSetUp.afterSetUp(self)
        # We need another folder and another zsyncer so we can more easily
        # not worry about wiping out stuff in the first folder.
        # First add a subfolder...
        self.folder.manage_addFolder('folder2')
        self.folder2 = self.folder.folder2
        # Now add a syncer in that folder...
        manage_addZSyncer(self.folder2, 'zs2')
        self.zs2 = self.folder2.zs2
        # Now use that syncer as the destination from our first syncer.
        self.destination = self.zs2.absolute_url()
        self.zs1.manage_changeProperties(dest_servers=self.destination)
        # Let's create a more-or-less identical object in folder2.
        _makeFile(self.file1_id, text=self.file1_text,
                  container=self.folder2)
        self.file1_copy = self.folder2[self.file1.getId()]
        # Let's create an Extra object (only in fol2).
        self.file_extra_text = 'extra extra read all about it.'
        _makeFile('file_extra', text=self.file_extra_text,
                  container=self.folder2)
        self.file_extra = self.folder2.file_extra
        # Let's create a Missing object (only in fol1).
        self.file_missing_text = 'missing persons destination unknown'
        _makeFile('file_missing', text=self.file_missing_text,
                  container=self.folder)
        self.file_missing = self.folder.file_missing
        # We need to commit the above ZODB changes so that they show up in
        # all server threads.
        transaction.commit()


class TestRemoteMethods(RemoteSetUp, ZSyncerSetUp,
                        ZopeTestCase.Sandboxed,
                        ZopeTestCase.ZopeTestCase):

    """Test everything that actually talks to the remote server.
    """

    def test_manage_diffObject(self):
        zs1 = self.zs1
        # First try to get one that's missing on the destination.
        path = self.zs1._getRelativePhysicalPath(self.file_missing)
        diffdict = zs1.manage_diffObject(path)
        self.failUnless(len(diffdict['error']) > 0)
        self.assertEqual(len(diffdict['diff']), 0)
        self.assertEqual(diffdict['dest'], 404)
        self.assertEqual(diffdict['source'], self.file_missing_text) 
        # Now try one that's in both places.
        path = zs1._getRelativePhysicalPath(self.file1)
        diffdict = zs1.manage_diffObject(path)
        self.assertEqual(diffdict['error'], '')
        self.failUnless(len(diffdict['diff']) > 1)
        self.assertEqual(diffdict['dest'], self.file1_text)
        self.assertEqual(diffdict['source'], self.file1_text)
        # Now try one that's missing from local - i.e. EXTRA.
        path = self.zs2._getRelativePhysicalPath(self.file_extra)
        diffdict = zs1.manage_diffObject(path)
        self.assertEqual(diffdict['source'], 404)
        self.failUnless(diffdict['error'])

    def test_compare_path(self):
        cp = self.zs1._compare_path
        # Try a nonexistent object.
        self.assertRaises(ZSyncerObjNotFound, cp,
                          'yes/we/have/no/bananas')
        # Try the root of each syncer.
        results = cp('')
        # They come back in an unsorted list.  Let's massage into a
        # dictionary so we can more easily inspect each one.
        result_dict = {}
        for r in results[1]:
            result_dict[r['id']] = r
        # Results for file1.
        self.assertEqual(result_dict[self.file1_id]['path'],
                         self.zs1._getRelativePhysicalPath(self.file1))
        self.assertEqual(result_dict[self.file1_id]['status'], ZSyncer.OK)
        self.assertEqual(result_dict[self.file1_id]['meta_type'], 'File')
        self.failUnless(result_dict[self.file1_id]['is_diffable'])
        # Results for other stuff that's only there for zs1.
        self.assertEqual(result_dict[self.folder2.getId()]['path'],
                         self.zs1._getRelativePhysicalPath(self.folder2))
        self.assertEqual(result_dict[self.folder2.getId()]['status'],
                         ZSyncer.MISSING)
        self.assertEqual(result_dict[self.folder2.getId()]['meta_type'],
                         'Folder')
        self.failIf(result_dict[self.folder2.getId()]['is_diffable'])
        self.assertEqual(result_dict['acl_users']['path'],
                         ('acl_users',))
        self.assertEqual(result_dict['acl_users']['status'],
                         ZSyncer.MISSING)
        self.assertEqual(result_dict['acl_users']['meta_type'],
                         'User Folder')
        self.failIf(result_dict['acl_users']['is_diffable'])
        # Results for the Extra file.
        self.assertEqual(result_dict[self.file_extra.getId()]['path'],
                         (self.file_extra.getId(),))
        self.assertEqual(result_dict[self.file_extra.getId()]['status'],
                         ZSyncer.EXTRA)
        self.assertEqual(result_dict[self.file_extra.getId()]['meta_type'],
                         'File')
        self.failIf(result_dict[self.file_extra.getId()]['is_diffable'])
        # Try one MISSING object directly... should get empty output.
        missing_results = cp(self.file_missing.getId())
        self.assertEqual(missing_results, ({}, []))
        # Try one EXTRA object directly... empty output.
        #self.assertRaises(ZSyncerObjNotFound, cp, self.file_extra.getId())
        extra_results = cp(self.file_extra.getId())
        self.assertEqual(extra_results, ({}, []))

        # Try the 'include_base' optional arg.
        self.assertRaises(ZSyncerObjNotFound, cp, 'no/such/file',
                          include_base=1)
        extra_info = cp(self.file_extra.getId(), include_base=1)
        self.assertEqual(extra_info[1], [])
        self.assertEqual(extra_info[0]['status'], ZSyncer.EXTRA)
        missing_results = cp(self.file_missing.getId(), include_base=1)
        self.assertEqual(missing_results[1], [])
        self.assertEqual(missing_results[0]['status'], ZSyncer.MISSING)

    def test_manage_compare(self):
        # Test non-recursive results.
        zs1 = self.zs1
        base, subs = zs1.manage_compare('')
        # These must be sorted by ID.
        expected_results = [{'id': 'acl_users', 'status': ZSyncer.MISSING},
                            {'id': self.file_extra.getId(),
                             'status': ZSyncer.EXTRA},
                            {'id': self.file_missing.getId(),
                             'status': ZSyncer.MISSING},
                            {'id': self.folder2.getId(),
                             'status': ZSyncer.MISSING},
                            {'id': self.file1_id,
                             'status': ZSyncer.OK},
                            ]
        # Now ready to test.
        for i in range(len(expected_results)):
            expected = expected_results[i]
            actual = subs[i]
            for key, value in expected.items():
                self.assertEqual(actual[key], value)
        # Test recursive option.
        # At first it should give the same results.
        rec_base, rec_subs = zs1.manage_compare('', recurse=1)
        self.assertEqual(rec_base, base)
        self.assertEqual(rec_subs, subs)
        # Now make recursion more interesting.
        # Add another level of subfolders and some more stuff...
        self.folder2.manage_addFolder('fol3')
        self.folder3 = self.folder2.fol3
        for fruit in ('apple', 'banana', 'pear'):
            _makeFile(id='file_%s' % fruit, text='',
                      container=self.folder3)
        # ... also need a fol. with same id in folder1 in order to
        # recurse successfully...
        self.folder.manage_addFolder('fol3')
        # ... commit all that...
        transaction.commit()
        # ... and try recursive comparison again.
        rec_base, rec_subs = zs1.manage_compare('', recurse=1)
        expected_results = [
            {'status': ZSyncer.MISSING, 'path': ('acl_users',)},
            {'status': ZSyncer.EXTRA, 'path': ('file_extra',)},
            {'status': ZSyncer.MISSING, 'path': ('file_missing',)},
            {'status': ZSyncer.OK,  'path': ('fol3',)},
            {'status': ZSyncer.EXTRA,  'path': ('fol3', 'file_apple')},
            {'status': ZSyncer.EXTRA,  'path': ('fol3', 'file_banana')},
            {'status': ZSyncer.EXTRA, 'path': ('fol3', 'file_pear')},
            {'status': ZSyncer.MISSING, 'path': ('folder2',)},
            {'status': ZSyncer.OK, 'path': ('some_file',)}
            ]
        # Sort those by path ...
        temp = [(e['path'], e) for e in expected_results]
        temp.sort()
        expected_result = [t[1] for t in temp]
        # ... and test them.
        for i in range(len(expected_results)):
            expected = expected_results[i]
            actual = rec_subs[i]
            for key, value in expected.items():
                self.assertEqual(actual[key], value)
        #self.assertEqual(rec_base, base)  # XXX last_mod_time slightly off???

    def test_getServerConn(self):
        conn = self.zs1._getServerConn(self.destination)
        # The ServerConn is our interface to the remote ZSyncer.
        # So e.g. it should have the same id.
        id = conn.getId()
        self.assertEqual(id, self.zs2.getId())

    def test_getRemoteList(self):
        server = self.zs1._getFirstDestination()
        result = self.zs1._getRemoteList(server, '')
        # It's a tuple of two dicts, as described by the docstring.
        folder2_info, sub_info = result
        self.assertEqual(folder2_info['id'], self.folder2.getId())
        def verify_dict(adict):
            # Helper to verify that the dictionaries have the right info.
            typemap = {'dc_modtime': (types.StringType, DateTime),
                       'icon': (types.StringType,),
                       'id': (types.StringType,),
                       'is_folder': (types.IntType, types.BooleanType),
                       'last_modified_time': (DateTime,),
                       'meta_type': (types.StringType,),
                       'path': (types.TupleType,),
                       'absolute_url_path': (types.StringType,),
                       'relative_path': (types.StringType,),
                       'id_or_path': (types.StringType,),
                       'size': (types.IntType, types.FloatType,
                                types.StringType),
                       }
            for key in typemap.keys():
                self.failUnless(adict.has_key(key))
            for key in adict.keys():
                self.failUnless(typemap.has_key(key))
                # Verify the types of values in the dict.
                for atype in typemap[key]:
                    if isinstance(adict[key], atype):
                        break  # We found a matching type.
                else:
                    self.fail('%s value %s is not an instance of any of %s' %
                              (key, adict[key], str(typemap[key])))
        verify_dict(folder2_info)
        # The sub info contains anything in folder 2.
        sub_keys = sub_info.keys()
        sub_keys.sort()
        expected_keys = self.folder2.objectIds('File') # leave out zs2
        expected_keys.sort()
        self.assertEqual(sub_keys, expected_keys)
        file_extra_info = sub_info[self.file_extra.getId()]
        verify_dict(file_extra_info)

    def test_srcRemote(self):
        path = self.file_extra.getId()
        data = self.zs1._srcRemote(self.destination, path)
        self.assertEqual(data, self.file_extra_text)
        # Try one that's not there.
        notfound_data = self.zs1._srcRemote(self.destination, 'no such thing')
        self.assertEqual(notfound_data, 404)
        # Try one that's not in our folder.
        self.assertRaises(ValueError, self.zs1._srcRemote,
                          self.destination, self.file1_path)

    def test_deleteRemote(self):
        notfound_response = self.zs1._deleteRemote(self.destination,
                                                  'no such thing')
        self.assertEqual(notfound_response, 404)
        notfound_response = self.zs1._deleteRemote(self.destination,
                                                   self.file_missing.getId())
        self.assertEqual(notfound_response, 404)
        # Now try to delete something real.  Since this makes a remote
        # call, we need to sync the zodb afterwards in order to see
        # the change in the main test thread.  We need a _p_jar to do
        # that, so let's do the subtransaction hack.
        try:
            transaction.commit(1)
            # Let's try one that is found relative to zs2.
            # Note that this is EXTRA from the point of view of zs1.
            response = self.zs1._deleteRemote(self.destination,
                                              self.file_extra.getId())
            extra_path = self.file_extra.getPhysicalPath()
            self.assertEqual(response, 200)
            # The object should no longer be there.
            self.app._p_jar.sync()
            self.assertRaises(KeyError, self.app.unrestrictedTraverse,
                              extra_path)
        finally:
            transaction.abort(1)

    def test_exportToRemote(self):
        path = self.zs1._getRelativePhysicalPath(self.file_missing)
        data = self.zs1.manage_getExportData(path)
        response = self.zs1._exportToRemote(self.destination, path,
                                           data)
        self.assertEqual(response, 200)
        # Object should show up after transaction commits and
        # sync the zodb. Fortunately, ZopeTestCase.Sandboxed does that
        # automatically.
        id = self.file_missing.getId()
        self.failUnless(id in self.folder2.objectIds())

    def test_callRemote(self):
        # Remote interface to callMethod_.
        server_url = self.zs1._getFirstDestination()
        # Try some simple stuff, like getId...
        id = self.zs1.callRemote(server_url, self.file_extra.getId(),
                                 'getId')
        self.assertEqual(id, self.file_extra.getId())
        # ... physical path...
        path = self.zs1.callRemote(server_url, self.file_extra.getId(),
                                   'getPhysicalPath')
        self.assertEqual(path, self.file_extra.getPhysicalPath())
        # Now try passing positional arguments...
        # first verify that the state is clean.
        self.assertEqual(self.zs1.callRemote(server_url,
                                             self.file_extra.getId(),
                                             'propertyIds'),
                         ['title', 'alt', 'content_type'])
        self.zs1.callRemote(server_url, self.file_extra.getId(),
                            'manage_addProperty',
                            'sillyFlag', 1, 'boolean')
        flag = self.zs1.callRemote(server_url, self.file_extra.getId(),
                                   'getProperty', 'sillyFlag')
        self.failUnless(flag)
        # Try passing keyword arguments.
        new_title = 'This is my new shiny title. It cost 50 cents.'
        self.zs1.callRemote(server_url, self.file_extra.getId(),
                            'manage_changeProperties',
                            title=new_title, sillyFlag=0)
        title = self.zs1.callRemote(server_url, self.file_extra.getId(),
                                    'getProperty', 'title')
        self.assertEqual(title, new_title)
        flag = self.zs1.callRemote(server_url, self.file_extra.getId(),
                                   'getProperty', 'sillyFlag')
        self.failIf(flag)
        # Try somethign that raises an exception on the server;
        # it should be re-raised locally.
        self.assertRaises(BadRequest,
                          self.zs1.callRemote,
                          server_url, self.file_extra.getId(),
                          'manage_delProperties',
                          ids=['bogosity'])
        # Try passing None as path; should get the syncer itself.
        self.assertEqual(self.zs1.callRemote(server_url, None, 'getId'),
                         self.zs2.getId())

    def test_callManyRemote(self):
        callMany = self.zs1.callManyRemote
        # First try one that doesn't exist.
        bogus = [{'path': 'somepath', 'name': 'somemethod'}]
        self.assertRaises(ZSyncerObjNotFound,
                          callMany, bogus)
        # Now try one method that takes no args and returns something.
        path = self.file_extra.getId()
        real_method = {'path': path,
                        'name': 'getId'}
        self.assertEqual(callMany([real_method]),
                         [self.file_extra.getId()]
                         )
        # Now try two methods at once, with positional and keyword args.
        methods = [
            {'path': path,
             'name': 'manage_upload',
             'kwargs': {'file': 'very fluffy'}
             },
            {'path': path,
             'name': 'manage_edit',
             'args': ['Cumulonimbus', 'text/plain'],
             },
            ]
        # Neither of those methods returns anything.
        self.assertEqual(callMany(methods), [None, None])
        # The object should be mutated.
        #self.assertEqual(self.file_extra.title, 'Cumulonimbus')
        self.assertEqual(self.file_extra.getContentType(), 'text/plain')
        self.assertEqual(self.file_extra.data, 'very fluffy')

        # Omitting the path should give us the remote syncer.
        self.assertEqual(callMany([{'name': 'getId'}]),
                         [self.zs2.getId()])
        # Same for passing None.
        self.assertEqual(callMany([{'name': 'getId', 'path': None}]),
                         [self.zs2.getId()])

    def test_manage_syncDelete(self):
        # Try deleting something that is only in folder2, i.e. EXTRA.
        extra_id = self.file_extra.getId()
        path = self.zs2._getRelativePhysicalPath(self.file_extra)
        # Need to sync the ZODB to see changes; fortunately,
        # Sandboxed takes care of that.
        self.failUnless(extra_id in self.folder2.objectIds())
        msgs = self.zs1.manage_syncDelete(path)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0].status, 200)
        self.assertEqual(msgs[1].status, 404)
        self.failIf(extra_id in self.folder2.objectIds())
        # Try a MISSING object.
        path = self.zs1._getRelativePhysicalPath(self.file_missing)
        missing_id = self.file_missing.getId()
        self.failUnless(missing_id in self.folder.objectIds())
        msgs = self.zs1.manage_syncDelete(path)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0].status, 404)
        self.assertEqual(msgs[1].status, 200)
        self.failIf(missing_id in self.folder.objectIds())
        # Try an OK object.
        # Again, Sandboxed takes care of the transaction.
        path = self.zs1._getRelativePhysicalPath(self.file1)
        self.failUnless(self.file1_id in self.folder.objectIds())
        self.failUnless(self.file1_id in self.folder2.objectIds())
        msgs = self.zs1.manage_syncDelete(path)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0].status, 200)
        self.assertEqual(msgs[1].status, 200)
        self.failIf(self.file1_id in self.folder.objectIds())
        self.failIf(self.file1_id in self.folder2.objectIds())


    def test_manage_pushToRemote(self):
        # Try an Extra object.
        path = self.zs2._getRelativePhysicalPath(self.file_extra)
        # No exception...
        msgs = self.zs1.manage_pushToRemote(path)
        self.assertEqual(len(msgs), 1)
        # ... but an error message in the output.
        self.assertEqual(msgs[0].status, 404)
        # Try a Missing object.
        # In order for the sync to show up in this thread, we need
        # to sync the ZODB, which Sandboxed does for us.
        path = self.zs1._getRelativePhysicalPath(self.file_missing)
        # No exception...
        msgs = self.zs1.manage_pushToRemote(path)
        self.assertEqual(len(msgs), 1)
        # ... and no error message in the output.
        self.assertEqual(msgs[0].status, 200)
        # The object should be in folder2 now.
        missing_id = self.file_missing.getId()
        self.failUnless(missing_id in self.folder2.objectIds())

    def test_manage_pullFromRemote(self):
        # Try a Missing object.
        folder, path = '', self.file_missing.getId()
        msgs = self.zs1.manage_pullFromRemote(path)
        self.assertEqual(len(msgs), 1)
        # ... server should report an error.
        self.assertEqual(msgs[0].status, 500)
        # Try an Extra object.
        folder, path = '', self.file_extra.getId()
        # First verify it's not in the folder...
        self.failIf(self.file_extra.getId() in self.folder.objectIds())
        msgs = self.zs1.manage_pullFromRemote(path)
        self.assertEqual(len(msgs), 1)
        # ... no error, and we should have the object locally now.
        self.assertEqual(msgs[0].status, 200)
        self.failUnless(self.file_extra.getId() in self.folder.objectIds())
##         # Try giving the folder name. This should be harmless, if
##         # useless.
##         new_msgs = self.zs1.manage_pullFromRemote(self.folder.getId(), path)
##         self.assertEqual(new_msgs, msgs)

    def test_manage_touch(self):
        missing_path = self.zs1._getRelativePhysicalPath(self.file_missing)
        # If we 'touch' something that is Missing, we get an exception
        # from the remote side.
        self.assertRaises(ZSyncerObjNotFound, self.zs1.manage_touch,
                          missing_path)
        # OK, what if we 'touch' something that is Extra?
        # The local server raises an exception.
        extra_path = self.zs2._getRelativePhysicalPath(self.file_extra)
        self.assertRaises(ZSyncerObjNotFound,
                          self.zs1.manage_touch, extra_path)
        # Finally, touch something that's in both places.
        msgs = self.zs1.manage_touch(self.file1.getId())
        self.failUnless(msgs)  # should be non-empty.
        for m in msgs:
            self.failIf(m.status > 200)


class MockZSyncer(ZSyncer.ZSyncer):

    # Replaces many methods with stubs that just return enough
    # info to tell you what was called.
    # Useful for minimal-dependency whitebox testing.

    # This is maybe a bit stupid, but then, so is manage_approvedAction.

    def _showArgs(self, name, args, kw):
        return name, args, kw

    def manage_pushToRemote(self, *args, **kw):
        return self._showArgs('manage_pushToRemote', args, kw)

    def manage_syncDelete(self, *args, **kw):
        return self._showArgs('manage_syncDelete', args, kw)

    def manage_pullFromRemote(self, *args, **kw):
        return self._showArgs('manage_pullFromRemote', args, kw)

    def manage_touch(self, *args, **kw):
        return self._showArgs('manage_touch', args, kw)

    def _error(self, *args, **kw):
        return "error!"


class TestManageApprovedAction(ZopeTestCase.ZopeTestCase):

    # Uses a mock version of ZSyncer so we don't have to
    # test everything end-to-end. We're just verifying that it calls
    # the correct methods with correct arguments.

    def test_manage_approvedAction(self):
        maa = MockZSyncer('zsyncer').manage_approvedAction
        self.assertEqual(maa(action='this is a meaningless string'),
                         'error!')
        expected_put = ('manage_pushToRemote', (['a', 'b'],),
                        {'REQUEST': {}, 'msgs': ['User: None', 'Comments: ']}
                        )
        self.assertEqual(maa(action='put', object_paths=['a', 'b']),
                         expected_put)

        expected_get = ('manage_pullFromRemote', ('foopath',),
                        {'REQUEST': {}, 'msgs': ['User: None', 'Comments: ']}
                        )
        self.assertEqual(maa(action='get', folder='fol1',
                             object_paths='foopath'),
                         expected_get)
        expected_touch = ('manage_touch', ('abc',),
                          {'REQUEST': {}, 'msgs': ['User: None',
                                                   'Comments: XYZ']})
        self.assertEqual(maa(action='touch', object_paths='abc',
                             comments='XYZ'),
                         expected_touch)


class TestUIFunctional(RemoteSetUp, ZSyncerSetUp,
                        ZopeTestCase.FunctionalTestCase):

    """Functional Tests of the ZMI UI.
    """

    # XXX need to add a lot more tests here.

    def afterSetUp(self):
        RemoteSetUp.afterSetUp(self)
        self.basic_auth = '%s:%s' % (user_name, user_password)

    def test_SyncFolder(self):
        url = self.folder.absolute_url_path() + '/sync_html'
        # Denied by default.
        response = self.publish(url)
        self.assertEqual(response.getStatus(), 401)
        # Try again with auth.
        response = self.publish(url, self.basic_auth)
        # There's only one zsyncer there, so we should get
        # redirected. (sourceforge bug 1325930)
        self.assertEqual(response.getStatus(), 302)
        # XXX is there a way to see where i get redirected to?
        
        # When there are 2 syncers, we should get a page
        # allowing to select them.
        manage_addZSyncer(self.app, 'another_zs')
        response2 = self.publish(url, self.basic_auth)
        self.assertEqual(response2.getStatus(), 200)
        expected_urls = utils.listSyncers(self.app)
        for url in expected_urls:
            self.failUnless(response2.getBody().count(url['url'])
                            )

def test_suite():
    from unittest import TestSuite, makeSuite
    suite = TestSuite()
    suite.addTest(makeSuite(TestUtils))
    suite.addTest(makeSuite(TestZSyncerBasics))
    suite.addTest(makeSuite(TestManageApprovedAction))
    suite.addTest(makeSuite(TestRemoteMethods))
    suite.addTest(makeSuite(TestUIFunctional))
    return suite

if __name__ == '__main__':
    framework()
