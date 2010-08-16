ZSyncer Overview

  This file is called a README for a reason: you really should read
  the whole thing :-)

  ZSyncer is a Zope 2 product that allows you to synchronize and compare
  objects from one zope (source) to another (destination).  It is a lot 
  more convenient than the old manual export / transfer / import procedure.

  ZSyncer supports SSL as well as insecure HTTP.  It uses your choice
  of several transport implementations.  (Note that the old XML-RPC
  transport has been removed, it was slow, offered no advantages, and
  eventually stopped working at all.)


Installation

  Place the ZSyncer directory in your zope Products directory as usual
  with product installation. You need to do this for all Zope servers
  that you wish to use as sources or destinations.

  Be sure that you can make HTTP connections from the source server to
  the destination server (and the Zope port). ZSyncer cannot work
  without this. Command-line http clients such as lynx or wget may be
  helpful for testing the connection.

  It is highly advisable to be sure that the system clock on all source
  and destination servers are synchronized or at least very close. 
  On Unix, NTP may be a very good idea.

Requirements


  Zope 2.7 is recommended.

  Zope 2.8 should work too, but there are two errors in the test suite;
  not sure if these translate to real-world problems.

  WARNING, Zope 2.9 is NOT supported yet.

  Zope 2.6.x should still work, but no guarantees.
  We will drop support for 2.6 or earlier very soon.


Upgrading from Earlier Versions

  ZSyncer is still unstable, in the sense that it may change
  drastically between releases.

  ZSyncer 0.7 is not compatible with earlier versions. You should
  upgrade ZSyncer on all of your source and destination servers
  simultaneously.

  You will also have to update your ZSyncer instance configuration
  if you are upgrading from 0.5.1 or earlier.
  You can either use the management interface to configure by hand,
  or simply visit http://yourzope:8080/path/to/your/syncer/upgrade
  for each of your ZSyncer instances. **WARNING**, this may
  delete some attributes and thus may make "downgrading" difficult,
  unless you take care to archive your configuration somewhere.
  Exporting the ZSyncer instance is advisable in case you need to
  revert to an old version.

  To upgrade automatically for *all* ZSyncer instances, the following
  script (untested) may help::

	root = container.restrictedTraverse('/')
	syncers = root.ZopeFind(root, obj_metatypes=['ZSyncer'], search_sub=1)
	for (id, zs) in syncers:
	    print zs.upgrade()
	return printed

  Or you can do it by hand; simply re-enter the list of destination servers.

  Also check permissions if you are upgrading from 0.5.1 or earlier,
  as we changed the permission name for 0.6.0-beta2.
  (It used to be "Use ZSyncer", it is now "ZSyncer: Use ZSyncer"
  following the emerging convention.)

  Also, we no longer provide the "override user" option.
  If you wish to override the current user when syncing, you
  must configure it in the server list using the syntax
  http://user:password@hostname/path.
  This way, you can use different users for each destination.


Usage

  ZSyncer is pretty self-explanatory. If you disagree, email the current
  maintainer and tell him why :-)
  Also try the "Help" button in the Zope management interface.

  ZSyncer now supports both "push" and "pull". You can push data from
  one server to a remote server. You can also "pull" data back in the
  other direction.

  Note that using "pull" generally results in false "out-of-date"
  status, because the pull updates the local objects' modification
  times and thus makes them appear to be newer than the remote
  objects.  (CMF / Plone / CPS content objects happily do not have
  this problem, as they have another application-level timestamp that
  we use.)

  We refer to the server that is making the request as the "source"
  server. The server(s) that it sends requests to are the "destination"
  servers. Destination servers are identified by URL.

  As of 0.6.0, it is now possible to configure your syncers to use
  relative paths.  This means that a syncer at host1:8080/folder1/syncer1
  can sync to host2:8080/folder2/syncer2, and objects from folder1 on
  host1 will be synced to folder2 on host2.  This is a new feature,
  please let me know if there are any problems.
  Note that the flag must currently be set on both source and destination
  servers in order to work correctly.

Changes

  As of 0.7.0, the "delete" feature will delete objects from
  both the remote AND local systems.

  The "sync" feature has been replaced with two actions: 
  "push" (uploads objects to the remote system, this is equivalent
  to the old "sync" action), and 
  "pull" (downloads objects from the remote system).

  Also as of 0.7.0, there is a new "callRemote()" method,
  with which you can call any method on the destination system
  and get its output, assuming you have sufficient permissions.
  There is no UI for this, but it may be useful for scripting.
  See the source code for more details.

Configuring Security

  Note that ZSyncer uses basic HTTP authentication.
  If you are concerned about the user's password being intercepted,
  you should ensure that at least one of the following is true:

  * the connection between source and destination is on a trusted
    private network or tunnel

  * your destination servers are accessible via HTTPS and you 
    configure ZSyncer on the source server to use only 
    the https:// URLs of the destination servers.

  For a given user to use ZSyncer, there are several things you must ensure:

  * the user has the same ID and password on both servers, OR
 
  * you override the username and password by using this URL sequence
    in the destination servers configuration::
    
        http://username:password@hostname:port/path


  * On the source server: 

    The user must have at least the following permissions in the 
    context of the syncer object:

    * Use ZSyncer

    * View Management Screens

    ... and the following permissions in the context of the objects 
    to sync or compare:


    * Import/Export Objects

    * Use ZSyncer

    * View Management Screens


  * On the destination server:

    The effective user must have the same permissions as described
    above for the source server.

    In addition, the effective user must have the "Delete Objects"
    permission in the context of the objects you want to sync.


CMF / Plone / CPS support

  We now have a simple ZSyncerTool wrapper for ZSyncer. It does not
  provide all the features of ZSyncer yet, but it does work.  You can
  use the Extensions/Install method to install it, or for Plone use
  PortalQuickInstaller.

  The provided CMF skins are currently very minimal, e.g. there isn't
  a working syncer view of all objects in a folder.  Also, these skins
  have only been tested with CMFDefault and *very* briefly with Plone
  2.1 so far.  The skins should basically work but you may want to
  customize or supplement them if you need more features.
  Contributions welcome!

  Another, possibly better, option would be to integrate ZSyncer into
  your workflow.  This is left as an excercise for the reader :-)

  Note that at this time, Plone's ATContentTypes are not supported
  by the "diff" feature. You can fix this by adding appropriate
  method names to the diff_methods dictionary in Config.py.

Configuring ZSyncerTool

  When you run the installer as described above, your CMF site gets a
  ZSyncerTool created. By default the tool contains one ZSyncer
  instance, named Default.
  This ZSyncer is preconfigured to use the CMF site as its
  base path. It does NOT have a destination configured (how could it
  guess?).  You must configure it yourself.
  The configuration is done on the ZSyncer instance ("Default"),
  not on the ZSyncerTool instance ("portal_zsyncer").

CMF Timezone bug:

  If you sync across multiple timezones, everything should "just
  work".  There was a problem prior to CMF 1.5.1 in that the
  folder_contents view defined by CMFDefault uses the Date()
  method of each object, which displayed the DublinCore modification
  time according to the timezone in which the object originated, but
  does not display the timezone. In CMF 1.5.1 this was fixed to
  convert the date into the local timezone before display.

Known Issues

  The "status" display can easily be wrong. We rely on
  bobobase_modification_time for objects that don't provide DublinCore
  timestamps.  This is not good. Among other things, it means that you
  frequently get "out of date" for no good reason.  Be suspicious of
  the status. Again, we recommend that you keep the clocks on your
  servers in sync. This will greatly reduce the likelihood of false
  status reports.

  "status" display for FilesystemDirectoryViews is meaningless.
  In debug mode, zope updates their bobobase_modification_time 
  periodically.

  See also the "Bugs" section of the TODO.txt.


Note on MonkeyPatches

  ZSyncer uses the "monkey patching" technique to dynamically
  modify a few things. This can be surprising, since it can change
  underlying behavior without visible changes to the source code
  of the monkeypatched module.

  Specifically:

  - we patch Python's httplib to allow us to set a timeout.
    Hopefully a future release of Python will make this 
    unnecessary.
 
  - we patch various Zope Products to add a Sync tab to the ZMI.
    (The patched classes are selected in Config.py.)

Unit Tests

  ZSyncer provides unit tests in the tests/ subdirectory.
  Actually many of them are integration tests. Let's not argue
  about that :-)

  The tests/test*.py files require that ZopeTestCase is installed.
  (See http://www.zope.org/Members/shh/ZopeTestCase)

  The ZSyncerTool tests also require that CMFTestCase is intalled.
  (See http://www.zope.org/Members/shh/CMFTestCase)

  To run the tests, you can do:

    python tests/runalltests.py

  Or to run individual test modules, you can do e.g.:

    python tests/test_ZSyncer.py

