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

__doc__ = '''Netfarm Archiver - release 2.x - XmlRpc backend'''
__version__ = '2.0a1'
__all__ = [ 'Backend' ]

from archiver import *
from sys import exc_info
from xmlrpc import client, fault, setLogLevel, setLogger
from urlparse import urlparse

class BadUrlSyntax(Exception):
    pass

### TODO 2.x this method is 100% ok??
def decode_url(url):
    res = urlparse(url)
    username, password = None, None
    if res[0].lower() != 'http':
        raise BadUrlSyntax
    
    if res[1].find('@')!=-1:
        try:
            auth_str, host_str = res[1].split('@', 1)
            username, password = auth_str.split(':', 1)
        except:
            raise BadUrlSyntax, url
    else:
        host_str = res[1]

    try:
        hostname, port = host_str.split(':', 1)
        port = int(port)
    except:
        raise BadUrlSyntax, url
        
    url = res[2]
    return hostname, port, url, username, password

class Backend(BackendBase):
    def __init__(self, config, stage_type, ar_globals):
        self.config = config
        self.type = stage_type
        self.LOG = ar_globals['LOG']
        try:
            setLogLevel(config.getint(self.type, 'loglevel'))
            setLogger(self.LOG['log_fd'])
        except:
            setLogLevel(0)
        url = config.get(self.type, 'url')
        self.hostname, self.port, self.url, self.username, self.password = decode_url(url)
        self.client = client(self.hostname, self.port)
        self.LOG(E_INFO, 'XmlRpc Backend (%s) at %s port %d url is %s' %
                 (self.type, self.hostname, self.port, self.url))
        del ar_globals
        
    def process(self, data):
        ### archive backend returns year as status and pid as code
        try:
            status, code = self.client.execute(self.url, [data], -1.0, self.username, self.password)
            return status, code, 'Ok'
        except:
            t, val, tb = exc_info()
            del tb
            if isinstance(val, fault):
                val = val.faultString
            return 0, 443, '%s: %s' % (t, val)
        
    def shutdown(self):
        self.LOG(E_INFO, 'XmlRpc Backend (%s): closing connection' % self.type)
        self.client = None
