#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2.x
#
# Copyright (C) 2004 Gianluigi Tiesi <sherpya@netfarm.it>
# Copyright (C) 2004 NetFarm S.r.l.  [http://www.netfarm.it]
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
## \file backend_filesystem.py
## \brief Filesystem Storage only Backend

__doc__ = '''Netfarm Archiver - release 2.x - Filesystem backend'''
__version__ = '2.0a1'
__all__ = [ 'Backend' ]

from archiver import *
from sys import exc_info
from os import path, access, makedirs, F_OK, R_OK, W_OK
from time import localtime

class BadStorageDir(Exception):
    """\brief Exception: Bad Storage directory in config file"""
    pass

class Backend(BackendBase):
    """\brief Filesystem Backend Class

    Stores emails on filesystem"""
    def __init__(self, config, stage_type, ar_globals):
        """The constructor"""
        self.config = config
        self.type = stage_type
        if self.type != 'storage':
            raise StorageTypeNotSupported, self.type
        
        self.LOG = ar_globals['LOG']
        self.storagedir = config.get(self.type, 'storagedir')
        
        if not access(self.storagedir, F_OK | R_OK | W_OK):
            raise BadStorageDir, self.storagedir
        
        self.LOG(E_ALWAYS, 'Filesystem Backend (%s) at %s ' % (self.type, self.storagedir))
        del ar_globals
                
    ### Storage on filesystem
    def process(self, data):
        month = data['date'][1]

        ### First check integrity
        mailpath = path.join(self.storagedir, str(data['year']), str(month))
        if not access(mailpath, F_OK | R_OK | W_OK):
            try:
                makedirs(mailpath, 0700)
            except:
                t, val, tb = exc_info()
                del tb
                self.LOG(E_ERR, 'Filesystem Backend: Cannot create storage directory: ' + str(val))
                return 0, 443, '%s: %s' % (t, val)
            
        try:
            filename = path.join(mailpath, str(data['pid']))
            fd = open(filename, 'w')
            fd.write(data['mail'])
            fd.flush()
            fd.close()
            self.LOG(E_TRACE, 'Filesystem Backend: wrote ' + filename)
            return BACKEND_OK
        except:
            t, val, tb = exc_info()
            del tb
            self.LOG(E_ERR, 'Filesystem Backend: Cannot write mail file: ' + str(val))
            return 0, 443, '%s: %s' % (t, val)

    def shutdown(self):
        """\brief Backend Shutdown callback"""
        self.LOG(E_ALWAYS, 'Filesystem Backend (%s): shutting down' % self.type)
