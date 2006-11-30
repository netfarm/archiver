#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2
#
# Copyright (C) 2005-2006 Gianluigi Tiesi <sherpya@netfarm.it>
# Copyright (C) 2006 Gianni Giaccherini   <jacketta@netfarm.it>
# Copyright (C) 2005-2006 NetFarm S.r.l.  [http://www.netfarm.it]
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
## @file backend_vfsimage.py
## VFS Image Storage only Backend

__doc__ = '''Netfarm Archiver - release 2.0.0 - VFS Image backend'''
__version__ = '2.0.0'
__all__ = [ 'Backend' ]

from archiver import *
from sys import platform, exc_info
from os import path, access, makedirs, stat, F_OK, R_OK, W_OK
from os import unlink, rename
from errno import ENOSPC
from ConfigParser import ConfigParser
from popen2 import Popen4
from compress import CompressedFile, compressors

### /etc/sudoers
# user ALL = NOPASSWD:/bin/mount,/bin/umount,/usr/bin/install

### Constants
cmd_mke2fs='/sbin/mke2fs -j -q -F -T news -L %(label)s -m 0 -O dir_index %(image)s'
cmd_tune2fs='/sbin/tune2fs -O ^has_journal %(image)s'
cmd_mount='/usr/bin/sudo /bin/mount -t ext3 -o loop %(image)s %(mountpoint)s'
cmd_umount='/usr/bin/sudo /bin/umount %(mountpoint)s'
cmd_prepare='/usr/bin/sudo /usr/bin/install -d -m 755 -o %(user)s %(mountpoint)s/%(archiverdir)s'

##
class VFSError(Exception):
    pass


class Backend(BackendBase):
    """VFS Image Backend Class

    Stores emails on filesystem image"""
    def __init__(self, config, stage_type, ar_globals):
        """The constructor"""
        self.config = config
        self.type = stage_type

        if self.type != 'storage':
            raise StorageTypeNotSupported, self.type

        self.LOG = ar_globals['LOG']
        self.user = ar_globals['runas']

        if platform.find('linux') == -1:
            raise VFSError, 'This backend only works on Linux'

        error = None
        try:
            self.image = config.get(self.type, 'image')
            self.mountpoint = config.get(self.type, 'mountpoint')
            self.infohashdb = config.get(self.type, 'infohashdb')
            self.archiverdir = config.get(self.type, 'archiverdir')
            self.imagesize = config.getint(self.type, 'imagesize')
        except:
            t, val, tb = exc_info()
            del t, tb
            error = str(val)

        if error is not None:
            self.LOG(E_ERR, 'Bad config file: %s' % error)
            raise BadConfig

        try:
            self.compression = config.get(self.type, 'compression')
        except:
            self.compression = None

        error = None
        if self.compression is not None:
            try:
                compressor, ratio = self.compression.split(':')
                ratio = int(ratio)
                if ratio < 0 or ratio > 9:
                    error = 'Invalid compression ratio'
                elif not compressors.has_key(compressor.lower()):
                    error = 'Compression type not supported'
                self.compressor = (compressor, ratio)
            except:
                pass

        if error is not None:
            self.LOG(E_ERR, 'Invalid compression option: %s' % self.compression)
            raise BadConfig, 'Invalid compression option'

        if not access(self.mountpoint, F_OK | R_OK | W_OK):
            self.LOG(E_ERR, 'VFS Image Backend (%s): Mount point is not accessible: %s' %
                     (self.type, self.mountpoint))
            raise VFSError, 'Mount point is not accessible'

        if self.isMounted():
            self.LOG(E_ERR, 'Image already mounted')
            if not self.umount():
                raise VFSError, 'Cannot umount image'

        isPresent = True
        try:
            stat(self.image)
        except:
            isPresent = False

        if isPresent and not self.initImage():
            raise VFSError, 'Cannot init Image'
        else:
            self.LOG(E_ALWAYS, 'VFS Image Backend (%s): Image init postponed ' % self.type)

        self.LOG(E_ALWAYS, 'VFS Image Backend (%s) at %s' % (self.type, self.image))

    def initImage(self):
        if not self.mount():
            self.LOG(E_ERR, 'VFS Image Backend (%s): Cannot mount image' % self.type)
            return False

        if not self.prepare():
            self.LOG(E_ERR, 'VFS Image Backend (%s): Image preparation failed' % self.type)
            return False

        return True

    def isMounted(self):
        try:
            mounts = open('/proc/mounts').readlines()
        except:
            self.LOG(E_ERR, 'Cannot open /proc/mounts, /proc not mounted?')
            return False

        for mp in mounts:
            mp = mp.strip().split()
            if mp[1] == self.mountpoint:
                return True
        return False

    def do_cmd(self, cmd, text):
        self.LOG(E_TRACE, 'VFS Image Backend (%s): Executing [%s]' % (self.type, cmd))
        pipe = Popen4(cmd)
        code = pipe.wait()
        res = pipe.fromchild.read()
        if code:
            self.LOG(E_ERR, 'VFS Image Backend (%s): %s (%s)' % (self.type, text, res.strip()))
            return False
        self.LOG(E_TRACE, 'VFS Image Backend (%s): Command output: [%s]' % (self.type, res.strip()))
        return True

    def mount(self):
        return self.do_cmd(cmd_mount % { 'image' : self.image, 'mountpoint' : self.mountpoint }, 'Cannot mount image')

    def umount(self):
        return self.do_cmd(cmd_umount % { 'mountpoint' : self.mountpoint }, 'Cannot umount image')

    def create(self, label):
        ## TODO: update image table
        try:
            fd = open(self.image, 'wb')
            fd.seek((self.imagesize * 1024 * 1024) - 1)
            fd.write(chr(0))
            fd.close()
        except:
            self.LOG(E_ERR, 'VFS Image Backend (%s): Cannot create the image file' % self.type)
            return False
        return self.do_cmd(cmd_mke2fs % { 'label' : label, 'image' : self.image }, 'Cannot make image')

    def prepare(self):
        return self.do_cmd(cmd_prepare % { 'user': self.user,
                                           'mountpoint': self.mountpoint,
                                           'archiverdir': self.archiverdir },
                           'Cannot prepare image for archiver')

    def reseal(self):
        return self.do_cmd(cmd_tune2fs % { 'image': self.image }, 'Cannot remove journal from image')

    def recycle(self):
        if not self.umount():
            self.LOG(E_ERR, 'VFS Image Backend (%s): Recycle: umount failed' % self.type)
            return False
            
        if not self.reseal():
            self.LOG(E_ERR, 'VFS Image Backend (%s): Recycle: reseal failed' % self.type)
            return False

        try:
            rename(self.image, 'FIXME')
            self.LOG(E_ERR, 'VFS Image Backend (%s): Recycle: rename failed' % self.type)
        except:
            return False

        return True

    ## Gets mailpath and filename
    def get_paths(self, data):
        month = data['date'][1]
        mailpath = path.join(self.mountpoint, self.archiverdir, str(data['year']), str(month))
        filename = path.join(mailpath, str(data['pid']))
        return mailpath, filename

    ## Storage on filesystem
    def process(self, data):
        mailpath, filename = self.get_paths(data)

        try:
            stat(self.image)
        except:
            self.LOG(E_ALWAYS, 'VFS Image Backend (%s): Image not present, creting it' % self.type)
            label = 'NMA-[%d-%d]' % (data['year'], data['pid'])
            if not self.create(label):
                self.LOG(E_ERR, 'VFS Image Backend (%s): Cannot create Image file' % self.type)
                return 0, 443, 'Internal Error (Image creation failed)'

            if not self.initImage():
                self.LOG(E_ERR, 'VFS Image Backend (%s): Cannot init Image' % self.type)
                return 0, 443, 'Internal Error (Cannot init Image)'

        error = None
        if not access(mailpath, F_OK | R_OK | W_OK):
            error = 'No access to mailpath'
            try:
                makedirs(mailpath, 0700)
                error = None
            except:
                t, val, tb = exc_info()
                del tb
                error = '%s: %s' % (t, val)
                self.LOG(E_ERR, 'VFS Image Backend (%s): Cannot create storage directory: %s' %
                         (self.type, str(val)))

        if error is not None:
            return 0, 443, error

        if self.compression is not None:
            name = '%d-%d' % (data['year'], data['pid'])
            comp = CompressedFile(compressor=self.compression[0], ratio=self.compression[1], name=name)
            comp.write(data['mail'])
            data['mail'] = comp.getdata()
            comp.close()

        try:
            fd = open(filename, 'wb')
            fd.write(data['mail'])
            fd.flush()
            fd.close()
            self.LOG(E_TRACE, 'VFS Image Backend (%s): wrote %s' % (self.type, filename))
            return BACKEND_OK
        except:
            t, val, tb = exc_info()
            del tb
            if val.errno == ENOSPC:
                try:
                    unlink(filename)
                except:
                    pass
                if not self.recycle():
                    self.LOG(E_ERR, 'VFS Image Backend (%s): Error recycling Image' % self.type)
                    return 0, 443, 'Internal Error (Recycling failed)'

                self.LOG(E_ALWAYS, 'VFS Image Backend (%s): Recycled Image File, write postponed' % self.type)
                return 0, 443, 'Recycling volume'

            self.LOG(E_ERR, 'VFS Image Backend (%s): Cannot write mail file: %s' % (self.type, str(val)))
            return 0, 443, '%s: %s' % (t, val)

    def shutdown(self):
        """Backend Shutdown callback"""
        self.LOG(E_ALWAYS, 'VFS Backend (%s): shutting down' % self.type)
        try:
            stat(self.image)
            self.umount()
        except:
            pass
