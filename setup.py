# Copyright (c) 2004 Paul M. Winkler and contributors.
# Portions copyright (c) 2010 Simplistix Ltd.
# See license.txt for license details.

import os
from setuptools import setup,find_packages

base_dir = os.path.dirname(__file__)

setup(
    name='Products.ZSyncer',
    version='1.0.4',
    author='Paul M. Winkler, Chris Withers',
    author_email='chris@simplistix.co.uk',
    description=("ZSyncer is a project that allows live zope objects "
                 "to be synchronized from one Zope to another without "
                 "doing the tedious export / transfer / import dance"),
    long_description=open(os.path.join(base_dir,'docs','description.txt')).read(),
    url='http://pypi.python.org/pypi/Products.ZSyncer',
    classifiers=[
    'Development Status :: 5 - Production/Stable',
    'Intended Audience :: Developers',
    ],    
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires = (
        'Zope2',
        ),
    extras_require=dict(
        test=[
            'httplib2',
            'testfixtures',
            ],
        )
    )
