# Copyright (c) 2004 Paul M. Winkler and contributors.
# Portions copyright (c) 2010 Simplistix Ltd.
# See license.txt for license details.

import os
from setuptools import setup,find_packages

base_dir = os.path.dirname(__file__)

setup(
    name='Products.ZSyncer',
    version='1.0dev',
    author='Paul M. Winkler, Chris Withers',
    author_email='chris@simplistix.co.uk',
    description="ZSyncer is a Zope 2 product that allows you to synchronize and compare objects from one zope (source) to another (destination)",
    long_description=open(os.path.join(base_dir,'docs','description.txt')).read(),
    url='http://pypi.python.org/pypi/Products.ZSyncer',
    classifiers=[
    'Development Status :: 5 - Production/Stable',
    'Intended Audience :: Developers',
    ],    
    packages=find_packages(),
    zip_safe=False,
    install_requires = (
        'Zope2',
        ),
    )
