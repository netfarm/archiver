#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2
#
# Copyright (C) 2005-2006 Gianluigi Tiesi <sherpya@netfarm.it>
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
## @file backend_xmlrpc.py
## XMLrpc Storage and Archive Backend

__doc__ = '''Netfarm Archiver - release 2.0.0 - XmlRpc backend'''
__version__ = '2.0.0'
__all__ = [ 'Backend' ]

from archiver import *
from sys import exc_info
from xmlrpclib import ServerProxy, Error
from urlparse import urlparse
from time import mktime

##
class BadUrlSyntax(Exception):
    """BadUrlSyntax Bad url syntax in config file"""
    pass

class Backend(BackendBase):
    """XMLrpc Backend using python-xmlrpc

    This backend can be used with a xmlrpc capable server like zope"""
    def __init__(self, config, stage_type, ar_globals):
        """The constructor"""
        self.config = config
        self.type = stage_type
        self.LOG = ar_globals['LOG']
        try:
            self.url = config.get(self.type, 'url')
            self.method = config.get(self.type, 'method')
            self.server = ServerProxy(self.url)
        except:
            raise BadConfig, 'Bad config in xmlrpc backend'

        self.LOG(E_ALWAYS, 'XmlRpc Backend (%s) at %s' % (self.type, self.url))

    def process(self, data):
        """Archive backend proces
        @param data: The data argument is a dict containing mail info and the mail itself
        @return: year as status and pid as code"""
        ## FIXME wrap with xmlrpc DateTime - time.struct_time objects cannot be marshalled
        data['m_date'] = mktime(data['m_date'])
        self.LOG(E_TRACE, 'XmlRpc Backend (%s): ready to process %s' % (self.type, data))
        try:
            getattr(self.server, self.method)({'data': data})
        except Error, v:
            del v ## FIXME Fill error
            return 0, 443, 'Error'

        return 0, 200, 'Ok'

    def shutdown(self):
        """Backend Shutdown callback"""
        self.LOG(E_ALWAYS, 'XmlRpc Backend (%s): closing connection' % self.type)
        self.server = None
