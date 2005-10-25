#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2
#
# Copyright (C) 2005 Gianluigi Tiesi <sherpya@netfarm.it>
# Copyright (C) 2005 NetFarm S.r.l.  [http://www.netfarm.it]
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
## @file backend_swishe.py
## Filesystem Storage + Swish-e interface

__doc__ = '''Netfarm Archiver - release 2.0.0 - Swish-e backend'''
__version__ = '2.0.0'
__all__ = [ 'Backend' ]

from archiver import *
if platform == 'win32':
    raise StorageTypeNotSupported, 'Swish-e backend not yet supported on win32'
from backend_filesystem import Backend as Backend_filesystem
from sys import exc_info
from os import path, symlink, access, F_OK, R_OK, W_OK
from time import localtime
from anydbm import open as opendb
from fcntl import flock, LOCK_EX, LOCK_UN

##
class BadSpoolDir(Exception):
    """BadSpoolDir Bad Swish-e spooling directory in config file"""
    pass

class Backend(Backend_filesystem):
    """Swish-e Class

    Stores emails on filesystem and make links for swish-e processing"""
    def __init__(self, config, stage_type, ar_globals):
        """The constructor"""
        self.config = config
        self.type = stage_type
        self.LOG = ar_globals['LOG']

        self.process = getattr(self, 'process_' + self.type, None)
        self.backend_init = getattr(self, 'init_' + self.type, None)
        if self.process is None or self.backend_init is None:
            raise StorageTypeNotSupported, self.type

        self.backend_init(ar_globals)

    def init_archive(self, unused):
        """Init Swish-e Archive Backend Class"""
        try:
            pidgenfile = self.config.get(self.type, 'pidgendb')
            self.pidgen = opendb(pidgenfile, 'c')
        except:
            raise Exception, 'Swish-e Archive Backend Cannot open pidgendb'

        self.LOG(E_ALWAYS, 'Swish-e Backend (%s) PidGeneration db at %s' % (self.type, pidgenfile))

    def init_storage(self, ar_globals):
        """Init Swish-e Storage Backend Class"""
        Backend_filesystem.__init__(self, self.config, self.type, ar_globals)
        self.process_filesystem = Backend_filesystem.process

        self.lock = None
        self.spooldir = self.config.get(self.type, 'spooldir')
        if not access(self.storagedir, F_OK | R_OK | W_OK):
            raise BadSpoolDir, self.spooldir

        self.lockfile = self.config.get(self.type, 'lockfile')

        self.LOG(E_ALWAYS, 'Swish-e Backend (%s) storage at %s spool at %s'
                 % (self.type, self.storagedir, self.spooldir))

    def lock(self):
        """Aquire lock to create symlink"""
        self.lock = open(self.lockfile, 'w')
        flock(self.lock, LOCK_EX)

    def unlock(self):
        """Release the lock"""
        if self.lock is None:
            self.LOG(E_ERR, 'Swish-e Backend (%s): Cannot release lockfile, there is no lock' % self.type)
        else:
            flock(self.lock, LOCK_UN)
            self.lock.close()
            self.lock = None

    def process_archive(self, unused):
        """Process archive

        Generates new year/pid pair and update the db with the new value"""
        year = localtime()[0]
        dbindex = str(year)
        newpid = 1
        if self.pidgen.has_key(dbindex):
            try:
                newpid = long(self.pidgen[dbindex])
            except:
                self.LOG(E_ERR, 'Swish-e Backend (%s): error getting pid, restarting from 1' % self.type)

        self.pidgen[dbindex] = str(newpid + 1)
        return year, newpid, 'OK'

    def process_storage(self, data):
        """Process storage

        first call Filesystem storage method,
        then symlink it to spool directory"""
        # First call Filesystem Backend
        res = self.process_filesystem(data)

        if res != BACKEND_OK:
            return res

        src  = self.get_paths(data)[1]
        dest = path.join(self.spooldir, '%s-%s' % (data['year'], data['pid']))

        # Aquire lock to write symlink
        self.lock()
        try:
            symlink(src, dest)
            # Release the lock
            self.unlock()
        except:
            t, val, tb = exc_info()
            del tb
            self.LOG(E_ERR, 'Swish-e Backend: Cannot symlink %s to %s - %s' % (src, dest, val))
            return 0, 443, '%s: %s' % (t, val)

    def shutdown(self):
        """Backend Shutdown callback"""
        self.LOG(E_ALWAYS, 'Swish-e Backend (%s): shutting down' % self.type)
