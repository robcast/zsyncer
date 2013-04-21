#
#    Copyright (c) 2004-2013, Corporation of Balclutha.
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

from Testing import ZopeTestCase
from Products.ZSyncer.ConnectionMgr import _MethodProxy as ConnectionMgr
from unittest import TestSuite, makeSuite


class TestConnectionMgr(ZopeTestCase.ZopeTestCase):
    '''Tries various things allowed by the ZopeTestCase API.'''


    def testNotJustDomain(self):
        conn = ConnectionMgr(('http://127.0.0.1/somewhere/syncer','',''),
                             'manage_listObjects')
        self.failUnless(1)



def test_suite():
    suite = TestSuite()
    suite.addTest(makeSuite(TestConnectionMgr))
    return suite


