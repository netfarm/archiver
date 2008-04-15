#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Generic MTP Server
# Copyright (C) 2005-2008 Gianluigi Tiesi <sherpya@netfarm.it>
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
## @file mtplib.py
## Generic Mail Trasfer Proxy

## Check 7/8bit stuff in headers

from sys import platform, hexversion
if platform != 'win32':
    from socket import AF_UNIX
from asynchat import async_chat, fifo
from asyncore import loop, dispatcher
from asyncore import close_all as asyncore_close_all
from socket import gethostbyaddr, gethostbyname, gethostname
from socket import socket, AF_INET, SOCK_STREAM
from sys import argv
from time import time, ctime
from os import unlink, chmod
import re

__all__ = [ 'MTPServer' ]
__version__ = 'Python Generic MTP Server version 0.2'

if hexversion < 0x02030000:
    raise Exception, 'Upgrade to python 2.3, this program needs python >= 2.3'

NEWLINE     = '\n'
QUOTE       = '\\'
EMPTYSTRING = ''
SPECIAL     = '<>()[]," '

re_rel  = re.compile(r"<@.*:(.*)>(.*)")
re_addr = re.compile(r"<(.*)>(.*)")
re_feat = re.compile(r"(?P<feature>[A-Za-z0-9][A-Za-z0-9\-]*)")

### Exceptions
##
class UnknownProtocol(Exception):
    """UnknownProtocol The selected protocol is not implemented"""
    pass

class BadPort(Exception):
    """BadPort The specified port is invalid"""
    pass

### Helpers
def check7bit(address):
    """check if an address is 7bit ascii

    Check if an address is 7bit ascii by encoding to charset ascii
    @param address: the address to check
    @return: 1 if the address is ok or 0 if the address is not 7bit ascii
    """
    try:
        address.encode('ascii')
        return True
    except:
        return False

def unquote(address, mapping=SPECIAL):
    """unquote a quoted address

    @param address: is the address to uquote
    @param mapping: is the special quoted char list
    @return: address unquoted"""
    for c in mapping + '\\':
        address = c.join(address.split(QUOTE + c))
    return address

def validate(address):
    """validate address syntax
    @param address: is the address to validate
    @return: the valid and unquoted address if ok or None"""
    for i in range(len(address)):
        if address[i] in SPECIAL:
            if i == 0 or address[i-1] != '\\':
                return None
    address = unquote(address)
    return address

### Envelope strict rfc821 check
def getaddr(keyword, arg):
    """strict rfc821 check for envelopes"""
    address = None
    options = None
    keylen = len(keyword)
    if arg[:keylen].upper() != keyword:
        return None, 'Bad command syntax'

    address = arg[keylen:].strip()

    ## Check for non 7bit
    if not check7bit(address):
        return None, 'Non 7bit'

    ## Relay regexp match
    res = re_rel.match(address)
    if res:
        address, options = res.groups()
    else:
        res = re_addr.match(address)
        if not res:
            return None, 'Unmatched regex'
        address, options = res.groups()

    ## Invalid space is needed
    if len(options) and options[0] != ' ':
        return None, 'Bad option syntax'

    options = options.strip()

    ## <> Null return path
    if len(address) < 3:
        return '', None

    if address.count('@')>1:
        return None, 'Too many @'

    ## Workaround to 'email@example.com'
    if address[0] == '\'' and address[-1] == '\'':
        address = address[1:-1]

    res = address.split('@', 1)
    address = validate(res[0])

    ## Invalid address
    if address is None:
        return None, 'Bad quoted sequence'

    ## Uh we have also a domain
    if len(res)>1:
        domain = validate(res[1])
        if domain:
            address = '@'.join([address, domain])

    return address, options

class MTPChannel(async_chat):
    """MTPChannel for communications with clients

    A subclass of async_chat, ideal to handle 'chat' like protocols"""
    COMMAND = 0
    DATA = 1
    def __init__(self, server, conn, addr, map=None):
        """The constructor"""
        self.ac_in_buffer = ''
        self.ac_out_buffer = ''
        self.producer_fifo = fifo()
        self.map = map
        dispatcher.__init__ (self, conn, self.map)
        self.__server = server
        self.__conn = conn
        self.__addr = addr
        self.__line = []
        self.__state = self.COMMAND
        self.__greeting = 0
        self.__mailfrom = None
        self.__mail_options = []
        self.__rcpttos = []
        self.__rcptopts = []
        self.__data = ''
        self.__fqdn = gethostbyaddr(gethostbyname(gethostname()))[0]
        self.__peer = conn.getpeername()
        self.push('220 %s %s' % (self.__fqdn, server.banner))
        self.set_terminator('\r\n')
        self.__getaddr = getaddr

    def push(self, msg):
        async_chat.push(self, msg + '\r\n')

    def collect_incoming_data(self, data):
        self.__line.append(data)

    def found_terminator(self):
        line = EMPTYSTRING.join(self.__line)
        self.__line = []
        if self.__state == self.COMMAND:
            if not line:
                self.push('500 5.5.2 Error: bad syntax')
                return
            method = None
            i = line.find(' ')
            if i < 0:
                command = line.upper()
                arg = None
            else:
                command = line[:i].upper()
                arg = line[i+1:].strip()
            method = getattr(self, 'impl_' + command, None)
            if not method:
                self.push('502 5.5.1 Error: command %s not implemented' % command)
                return
            method(arg)
            return
        else:
            if self.__state != self.DATA:
                self.push('451 4.3.0 Internal confusion')
                return
            ## Remove extraneous carriage returns and de-transparency according
            ## to RFC 821, Section 4.5.2.
            data = []
            for text in line.split('\r\n'):
                if text and text[0] == '.':
                    data.append(text[1:])
                else:
                    data.append(text)
            self.__data = NEWLINE.join(data)
            status = self.__server.process_message(self.__peer,
                                                   self.__mailfrom,
                                                   self.__mail_options,
                                                   self.__rcpttos,
                                                   self.__rcptopts,
                                                   self.__data)
            self.__rcpttos = []
            self.__rcptopts = []
            self.__mailfrom = None
            self.__mail_options = []
            self.__state = self.COMMAND
            self.set_terminator('\r\n')
            if not status:
                self.push('250 2.0.0 Ok')
            else:
                self.push(status)

    def close(self):
        """Close the channel and the socket"""
        self.del_channel(self.map)
        self.socket.close()

    ## Should I close the channel here?
    def handle_expt(self):
        pass

    # commands implementation
    def impl_HELO(self, arg):
        if not arg:
            self.push('500 5.5.2 Syntax: HELO hostname')
            return
        if self.__greeting:
            self.push('501 5.5.1 Duplicate HELO')
        else:
            self.__greeting = arg
            self.push('250-%s' % self.__fqdn)

    def impl_EHLO(self, arg):
        if not arg:
            self.push('500 5.5.2 Syntax: EHLO hostname')
            return
        if self.__greeting:
            self.push('501 5.5.1 Duplicate EHLO')
        else:
            self.__greeting = arg
            self.__emtp = True
            self.push('250-%s' % self.__fqdn)
            self.push('250 DSN')

    def impl_NOOP(self, arg):
        if arg:
            self.push('500 5.5.2 Syntax: NOOP')
        else:
            self.push('250 2.0.0 Ok')

    def impl_QUIT(self, arg):
        del arg
        self.push('221 2.0.0 Bye')
        self.close_when_done()

    def impl_RSET(self, arg):
        del arg
        self.__line = []
        self.__state = self.COMMAND
        self.__mailfrom = None
        self.__mail_options = []
        self.__rcpttos = []
        self.__rcptopts = []
        self.__data = ''
        self.__emtp = False
        self.push('250 2.0.0 Ok')

    def impl_MAIL(self, arg):
        address, options = self.__getaddr('FROM:', arg)
        if address is None:
            self.push('500 5.5.2 Syntax: MAIL FROM:<address> [ SP <mail-parameters> ]')
            return
        if self.__mailfrom:
            self.push('503 5.5.1 Error: nested MAIL command')
            return
        self.__mailfrom = address
        if options: self.__mail_options.append((address, options))
        self.push('250 2.0.0 Ok')

    def impl_RCPT(self, arg):
        if self.__mailfrom is None:
            self.push('503 5.5.1 Error: need MAIL command')
            return
        address, options = self.__getaddr('TO:', arg)
        if not address:
            self.push('500 5.5.2 Syntax: RCPT TO: <address> [ SP <rcpt-parameters> ]')
            return
        self.__rcpttos.append(address)
        if options: self.__rcptopts.append((address, options))
        self.push('250 2.0.0 Ok')

    def impl_DATA(self, arg):
        if not self.__rcpttos:
            self.push('503 5.5.1 Error: need RCPT command')
            return
        if arg:
            self.push('500 5.5.2 Syntax: DATA')
            return
        self.__state = self.DATA
        self.set_terminator('\r\n.\r\n')
        self.push('354 End data with <CR><LF>.<CR><LF>')

class MTPServer(dispatcher):
    """MTPServer dispatcher class implemented as asyncore dispatcher"""
    def __init__(self, localaddr, del_hook = None, timeout = None):
        """The Constructor

        Creates the listening socket"""
        self.debuglevel = 0
        self.loop = loop
        self.banner = __version__
        self.del_hook = del_hook
        if localaddr.find(':') == -1:
            raise UnknownProtocol, localaddr

        dispatcher.__init__(self)
        proto, params = localaddr.split(':', 1)

        ### UNIX
        if proto == 'unix':
            if platform == 'win32':
                raise Exception, 'Cannot use unix sockets on win32 platform'
            try:
                unlink(params)
            except:
                pass
            self.create_socket(AF_UNIX, SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.bind(params)
            try:
                chmod(params, 0777) ## FIXME hardcoded permissions ??
            except: pass
            ## Make asyncore __repr__ happy
            proto += ':' + params
            params = 0
        ### TCP
        else:
            try:
                port = int(params)
            except:
                port = 0

            if port == 0: raise BadPort, params
            self.create_socket(AF_INET, SOCK_STREAM)
            self.set_reuse_addr()
            self.socket.settimeout(timeout)
            self.bind((proto, port))
            params = port

        self.localaddr = (proto, params)
        self.addr = (proto, params)
        self.map = { self.socket.fileno(): self }

        self.listen(5)

    def writable(self):
        """Workaround for unix sockets with select/poll"""
        return 0

    def close(self):
        """Close the channel and the socket"""
        self.del_channel(self.map)
        self.socket.close()
        if self.localaddr[1]==0:
            try:
                unlink(self.localaddr[0].split(':',1).pop())
            except: pass

    def close_all(self):
        """closes all connections"""
        asyncore_close_all(self.map)

    def handle_accept(self):
        """handle client connections
        gracefully shutdown if some signal has interrupted self.accept()"""
        try:
            conn, addr = self.accept()
            channel = MTPChannel(self, conn, addr, self.map)
            channel.debuglevel = self.debuglevel
            if self.del_hook: channel.__del__ = self.del_hook
        except: pass

    # API for "doing something useful with the message"
    def process_message(self, peer, mailfrom, mail_options, rcpttos, rcptopts, data):
        raise NotImplementedError
