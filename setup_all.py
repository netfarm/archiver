#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2
#
# Copyright (C) 2005-2007 Gianluigi Tiesi <sherpya@netfarm.it>
# Copyright (C) 2005-2007 NetFarm S.r.l.  [http://www.netfarm.it]
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTIBILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
# for more details.
# ======================================================================
## @file setup_all.py
## Netfarm Mail Archiver [py2exe]

import sys, os, glob
sys.path.append('.')

try:
    import modulefinder
except ImportError:
    pass

from distutils.core import setup
import py2exe

backends = [ 'backend_filesystem', 'backend_rdbms', 'backend_rdbms', 'backend_xmlrpc', 'backend_vfsimage.py' ]
psycopg = [ 'psycopg', 'mx.DateTime']
deps = backends + psycopg + ['lmtp'] + ['dbhash']

py2exe_options = dict(
    excludes = '',
    optimize = '02',
    compressed = '1',
    includes = deps
)

nma = dict(
    company_name = 'Netfarm S.r.l.',
    copyright = 'Copyright (C) 2007 Gianluigi Tiesi',
    comments = 'Netfarm Mail Archiver',
    icon_resources = [(1, "nma.ico")],
    modules = ['archiver_svc']
)

archiver = dict(
    company_name = 'Netfarm S.r.l.',
    copyright = 'Copyright (C) 2007 Gianluigi Tiesi',
    comments = 'Netfarm Mail Archiver',
    icon_resources = [(1, "nma.ico")],
    script = 'archiver.py'
)

if len(sys.argv)==1 or \
   (len(sys.argv)==2 and sys.argv[1] in ['-q', '-n']):
    sys.argv.append("py2exe")

setup(name = "nma.py",
      version = "2.0.0",
      description = "Netfarm Mail Archiver",
      service = [nma],
      console = [archiver],
      options = {"py2exe" : py2exe_options},
      zipfile = "nma.zip",
)
