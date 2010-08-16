#
#    Copyright (c) 2004, Corporation of Balclutha.
#
#    Please report any bugs or errors in this program to our bugtracker
#    at http://www.last-bastion.net/HelpDesk
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#
#
import os, sys
if __name__ == '__main__':
    execfile(os.path.join(sys.path[0], 'framework.py'))

from Testing import ZopeTestCase
from Products.ZSyncer.ConnectionMgr import _MethodProxy as ConnectionMgr


class TestConnectionMgr(ZopeTestCase.ZopeTestCase):
    '''Tries various things allowed by the ZopeTestCase API.'''

    def testDomainURI(self):
        conn = ConnectionMgr(('https://monitor.last-bastion.net','',''),
                             'manage_listObjects')
        self.assertEqual(conn._v_conn.host, 'monitor.last-bastion.net')
        self.assertEqual(conn._v_conn.port, 443)

    def testIPURI(self):
        conn = ConnectionMgr(('http://127.0.0.1:666','',''),
                             'manage_listObjects')
        self.assertEqual(conn._v_conn.host, '127.0.0.1')
        self.assertEqual(conn._v_conn.port, 666)

    def testNotJustDomain(self):
        conn = ConnectionMgr(('http://127.0.0.1/somewhere/syncer','',''),
                             'manage_listObjects')
        self.failUnless(1)

    def testBadProtocol(self):
        self.assertRaises(AssertionError, ConnectionMgr,
                          ('ldap://localhost','',''), 'manage_listObjects')

    def testAuthHeader(self):
        conn = ConnectionMgr(('http://127.0.0.1/ZSyncer', 'bill', 'secret'),
                             'manage_listObjects')
        self.assertEqual(conn.headers['Authorization'],
                         'Basic YmlsbDpzZWNyZXQ=\n')


if __name__ == '__main__':
    framework()
else:
    # While framework.py provides its own test_suite()
    # method the testrunner utility does not.
    from unittest import TestSuite, makeSuite
    def test_suite():
        suite = TestSuite()
        suite.addTest(makeSuite(TestConnectionMgr))
        return suite


