#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2
#
# Copyright (C) 2005-2006 Gianluigi Tiesi <sherpya@netfarm.it>
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
## @file compress.py
## Helper for file compression

__doc__ = '''Netfarm Archiver - release 2.0.0 - Helper for file compression'''
__version__ = '2.0.0'
__all__ = [ 'CompressedFile', 'compressors' ]

from cStringIO import StringIO

compressors = {}

## Gzip File support
try:
    from gzip import GzipFile
    compressors.update({'gzip': 'GzipCompressedFile'})
except:
    pass

## Zip File support
try:
    import zlib
    from zipfile import ZipFile
    from zipfile import ZIP_STORED, ZIP_DEFLATED
    compressors.update({'zip': 'ZipCompressedFile'})
except:
    pass

## BZip2 File support
try:
    from bz2 import BZ2Compressor
    compressors.update({'bzip2': 'BZip2CompressedFile'})
except:
    pass

class UnsupportedCompressor(Exception):
    pass

class InvalidMethod(Exception):
    pass

class GzipCompressedFile:
    def __init__(self, **args):
        self.data = StringIO()
        self.classobj = GzipFile(args.get('name'), 'wb', args.get('method'), self.data)

    def write(self, data):
        self.classobj.write(data)

    def getdata(self):
        self.classobj.close()
        return self.data.getvalue()

    def close(self):
        self.data.close()

    def __del__(self):
        try:
            self.data.close()
            self.close()
        except:
            pass

class ZipCompressedFile:
    def __init__(self, **args):
        self.data = StringIO()
        self.name = args.get('name')
        if args.get('method') > 0:
            method = ZIP_DEFLATED
        else:
            method = ZIP_STORED

        self.classobj = ZipFile(self.data, 'wb', method)

    def write(self, data):
        self.classobj.writestr(self.name, data)

    def getdata(self):
        self.classobj.close()
        return self.data.getvalue()

    def close(self):
        self.data.close()

    def __del__(self):
        try:
            self.close()
        except:
            pass

class BZip2CompressedFile:
    def __init__(self, **args):
        self.classobj = BZ2Compressor(args.get('method'))

    def write(self, data):
        self.classobj.compress(data)

    def getdata(self):
        return self.classobj.flush()

    def close(self):
        pass

class CompressedFile:
    def __init__(self, **args):
        compressor = args.get('compressor', None)
        if compressor is None or not compressors.has_key(compressor):
            raise UnsupportedCompressor
        args['name'] = args.get('name', 'Unnamed')

        method = None
        try:
            method = int(args.get('method', 9))
        except:
            pass
        if method is None:
            raise InvalidMethod

        args['method'] = method
        compclass = globals().get(compressors[compressor])
        CompressedFile.__bases__ += (compclass,)
        compclass.__init__(self, **args)
