#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# LMTP Client/Server python implementation
# SMTP Server using same routines
# - Some code (server) taken form smtpd.py, shipped with python
# - Base code (client) taken from spamcheck.py (c) James Henstridg
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
## @file lmtp.py
## lmtp/smtp client/server implementation

## TODO 8BITMIME - should work normal way?
## Check 7/8bit stuff in headers
## TODO: does PIPELINING is server "transparent"?
## TODO: Add PureProxy as in smtpd.py ??

from sys import platform
if platform != 'win32':
    from socket import AF_UNIX
from asynchat import async_chat, fifo
from asyncore import loop,dispatcher
from asyncore import close_all as asyn_close_all
from socket import gethostbyaddr, gethostbyname, gethostname
from socket import socket, AF_INET, SOCK_STREAM
from smtplib import SMTP, SMTPConnectError, SMTPServerDisconnected
from smtpd import SMTPChannel as smtpd_SMTPChannel
from sys import argv
from time import time, ctime
from os import unlink, chmod
import re

__all__ = ["LMTPServer", "SMTPServer", "DebuggingServer"]
__version__ = 'Python LMTP Server version 0.1'

NEWLINE = '\n'
QUOTE='\\'
EMPTYSTRING = ''
SPECIAL='<>()[]," '
LMTP_PORT=2003
DEBUG=1

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
        return 1
    except:
        return 0

def unquote(address, map=SPECIAL):
    """unquote a quoted address

    @param address: is the address to uquote
    @param map: is the special quoted char list
    @return: address unquoted"""
    for c in map+'\\':
        address = c.join(address.split(QUOTE+c))
    return address

def validate(address):
    """validate address syntax
    @param address: is the address to validate
    @return: the valid and unquoted address if ok or None"""
    for i in range(len(address)):
        if address[i] in SPECIAL:
            if i==0 or address[i-1] != '\\':
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
    if len(address)<3:
        return '', None

    if address.count('@')>1:
        return None, 'Too many @'

    ## Workaround to 'email@example.com'
    if address[0]=='\'' and address[-1]=='\'':
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

### LMTP Client Class
class LMTP(SMTP):
    """LMTP Base Class

    this class hacks smtplib's SMTP class into a shape where it will
    successfully pass a message off to Cyrus's LMTP daemon.
    Also adds support for connecting to a unix domain socket (unix platform only)."""

    lhlo_resp = None
    def __init__(self, host='', port=0):
        """The constructor"""
        self.lmtp_features  = {}
        self.esmtp_features = self.lmtp_features
        if host:
            (code, msg) = self.connect(host, port)
            if code != 220:
                raise SMTPConnectError(code, msg)

    def connect(self, host='localhost', port=LMTP_PORT):
        """Connect to a host on a given port.

        If the hostname starts with `unix:', the remainder of the string
        is assumed to be a unix domain socket.
        """
        if host[:5] == 'unix:':
            if platform == 'win32':
                raise Exception, 'Cannot use unix sockets on win32 platform'
            host = host[5:]
            self.sock = socket(AF_UNIX, SOCK_STREAM)
            if self.debuglevel > 0: print 'connect:', host
            self.sock.connect(host)
        else:
            self.sock = socket(AF_INET, SOCK_STREAM)
            if self.debuglevel > 0: print 'connect:', (host, port)
            self.sock.connect((host, port))

        (code, msg) = self.getreply()
        if self.debuglevel > 0: print 'connect:', msg
        return (code, msg)

    def lhlo(self, name='localhost'):
        """ LMTP 'lhlo' command.

        Hostname to send for this command defaults to localhost.
        """
        self.putcmd("lhlo",name)
        (code, msg) = self.getreply()
        if code == -1 and len(msg) == 0:
            raise SMTPServerDisconnected("Server not connected")
        self.lhlo_resp = msg
        self.ehlo_resp = msg
        if code != 250:
            return (code, msg)
        self.does_esmtp = 1
        ## parse the lhlo response
        resp = self.lhlo_resp.split('\n')
        del resp[0]
        for each in resp:
            m = re_feat.match(each)
            if m:
                feature = m.group("feature").lower()
                params = m.string[m.end("feature"):].strip()
                self.lmtp_features[feature] = params
        return (code, msg)

    ## "re-route" non lmtp commands
    helo = lhlo
    ehlo = lhlo

### LMTP Server Stuff
class LMTPChannel(async_chat):
    """LMTPChannel for communications with clients

    A subclass of async_chat, ideal to handle "chat" like protocols"""
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
        self.__rcpttos = []
        self.__data = ''
        self.__8bit = None
        self.__fqdn = gethostbyaddr(gethostbyname(gethostname()))[0]
        self.__peer = conn.getpeername()
        self.push('220 %s %s' % (self.__fqdn, server.banner))
        self.set_terminator('\r\n')
        self.__getaddr = getaddr

    def push(self, msg):
        """Overrides base class for convenience"""
        async_chat.push(self, msg + '\r\n')

    def collect_incoming_data(self, data):
        """Implementation of base class abstract method"""
        self.__line.append(data)

    def found_terminator(self):
        """Implementation of base class abstract method"""
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
            method = getattr(self, 'lmtp_' + command, None)
            if not method:
                self.push('502 5.5.1 Error: command "%s" not implemented' % command)
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
                                                   self.__rcpttos,
                                                   self.__data)
            self.__rcpttos = []
            self.__mailfrom = None
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

    # LMTP commands
    def lmtp_LHLO(self, arg):
        """ LMTP LHLO Command implementation"""
        if not arg:
            self.push('500 5.5.2 Syntax: LHLO hostname')
            return
        if self.__greeting:
            self.push('501 5.5.1 Duplicate LHLO')
        else:
            self.__greeting = arg
            self.push('250-%s' % self.__fqdn)
            self.push('250-8BITMIME')
            self.push('250-ENHANCEDSTATUSCODES')
            self.push('250 PIPELINING')

    def lmtp_NOOP(self, arg):
        """ LMTP NOOP Command implementation"""
        if arg:
            self.push('500 5.5.2 Syntax: NOOP')
        else:
            self.push('250 2.0.0 Ok')

    def lmtp_QUIT(self, arg):
        """ LMTP QUIT Command implementation"""
        del arg
        self.push('221 2.0.0 Bye')
        self.close_when_done()

    def lmtp_RSET(self, arg):
        """ LMTP RSET Command implementation"""
        del arg
        self.__line = []
        self.__state = self.COMMAND
        self.__mailfrom = None
        self.__rcpttos = []
        self.__data = ''
        self.__8bit = None
        self.push('250 2.0.0 Ok')

    def lmtp_MAIL(self, arg):
        """ LMTP MAIL Command implementation"""
        address, options = self.__getaddr('FROM:', arg)
        if address is None:
            self.push('500 5.5.2 Syntax: MAIL FROM:<address> [ SP <mail-parameters> ]')
            return
        if self.__mailfrom:
            self.push('503 5.5.1 Error: nested MAIL command')
            return
        self.__mailfrom = address
        if options and options.upper() == "BODY=8BITMIME":
            self.__8bit = 1
            self.push('250 2.0.0 Ok - Body 8bitmime ok')
        else:
            self.push('250 2.0.0 Ok')

    def lmtp_RCPT(self, arg):
        """ LMTP RCPT Command implementation"""
        if not self.__mailfrom:
            self.push('503 5.5.1 Error: need MAIL command')
            return
        address, options = self.__getaddr('TO:', arg)
        if options or not address:
            self.push('500 5.5.2 Syntax: RCPT TO: <address> [ SP <rcpt-parameters> ]')
            return
        self.__rcpttos.append(address)
        self.push('250 2.0.0 Ok')

    def lmtp_BDAT(self, arg):
        """ LMTP BDAT Command implementation [Not implemented]"""
        del arg
        self.push('502 5.5.1 BDAT not implemented')

    def lmtp_DATA(self, arg):
        """ LMTP DATA Command implementation"""
        if not self.__rcpttos:
            self.push('503 5.5.1 Error: need RCPT command')
            return
        if arg:
            self.push('500 5.5.2 Syntax: DATA')
            return
        self.__state = self.DATA
        self.set_terminator('\r\n.\r\n')
        self.push('354 End data with <CR><LF>.<CR><LF>')

class LMTPServer(dispatcher):
    """LMTPServer dispatcher class implemented as asyncore dispatcher"""
    def __init__(self, localaddr, del_hook=None, timeout=None):
        """The Constructor

        Creates the listening socket"""
        self.debuglevel = 0
        self.loop = loop
        self.banner = __version__
        self.del_hook = del_hook
        if localaddr.find(':')==-1:
            raise UnknownProtocol, localaddr

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

            if getattr(self.socket, 'settimeout', None) is not None:
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
                params = int(params)
            except:
                raise BadPort, params
            self.create_socket(AF_INET, SOCK_STREAM)
            self.set_reuse_addr()

            if getattr(self.socket, 'settimeout', None) is not None:
                self.socket.settimeout(timeout)

            self.bind((proto, params))

        self.localaddr = (proto, params)
        self.addr = (proto, params)
        self.map = { self.socket.fileno(): self }
        dispatcher.__init__(self, self.socket, self.map)
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
        asyn_close_all(self.map)

    def handle_accept(self):
        """handle client connections
        gracefully shutdown if some signal has interrupted self.accept()"""
        try:
            conn, addr = self.accept()
            channel = LMTPChannel(self, conn, addr, self.map)
            channel.debuglevel = self.debuglevel
            if self.del_hook: channel.__del__ = self.del_hook
        except: pass

    # API for "doing something useful with the message"
    def process_message(self, peer, mailfrom, rcpttos, data):
        """Override this abstract method to handle messages from the client.

        peer is a tuple containing (ipaddr, port) of the client that made the
        socket connection to our lmtp port.
        peer is None for unix sockets.

        mailfrom is the raw address the client claims the message is coming
        from.

        rcpttos is a list of raw addresses the client wishes to deliver the
        message to.

        data is a string containing the entire full text of the message,
        headers (if supplied) and all.  It has been `de-transparencied'
        according to RFC 821, Section 4.5.2.  In other words, a line
        containing a `.' followed by other text has had the leading dot
        removed.

        This function should return None, for a normal `250 Ok' response;
        otherwise it returns the desired response string in RFC 821 format.

        """
        raise NotImplementedError

### SMTP Server stuff
class SMTPChannel(smtpd_SMTPChannel):
    """Communication channel to handle a chat-style connection"""
    COMMAND = 0
    DATA = 1
    def __init__(self, server, conn, addr, map=None):
        """The constructor"""
        self.debuglevel = 0
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
        self.__rcpttos = []
        self.__data = ''
        self.__fqdn = gethostbyaddr(gethostbyname(gethostname()))[0]
        self.__peer = conn.getpeername()
        self.push('220 %s %s' % (self.__fqdn, server.banner))
        self.set_terminator('\r\n')
        self.__getaddr = getaddr

    def smtp_MAIL(self, arg):
        """SMTP 'mail' command"""
        address, options = self.__getaddr('FROM:', arg)
        if address is None:
            self.push('500 5.5.2 Syntax: MAIL FROM:<address> [ SP <mail-parameters> ]')
            return
        if self.__mailfrom is not None:
            self.push('503 5.5.1 Error: nested MAIL command')
            return
        self.__mailfrom = address
        if options and options.upper() == "BODY=8BITMIME":
            self.__8bit = 1
            self.push('250 2.0.0 Ok - Body 8bitmime ok')
        else:
            self.push('250 2.0.0 Ok')

    def smtp_RCPT(self, arg):
        """SMTP 'rcpt' command"""
        if self.__mailfrom is None:
            self.push('503 5.5.1 Error: need MAIL command')
            return
        address, options = self.__getaddr('TO:', arg)
        if options or not address:
            self.push('500 5.5.2 Syntax: RCPT TO: <address> [ SP <rcpt-parameters> ]')
            return
        self.__rcpttos.append(address)
        self.push('250 2.0.0 Ok')

    def close(self):
        """Close the channel and the socket"""
        self.del_channel(self.map)
        self.socket.close()

class SMTPServer(LMTPServer):
    """Async Server, it handle the connection using SMTPChannel"""
    def handle_accept(self):
        ### gracefully shutdown if some signal has interrupted self.accept()
        try:
            conn, addr = self.accept()
            channel = SMTPChannel(self, conn, addr, self.map)
            channel.debuglevel = self.debuglevel
            if self.del_hook: channel.__del__ = self.del_hook
        except: pass

class DebuggingServer(LMTPServer):
    """DebuggingServer based on LMTPServer"""
    def __init__(self, localaddr):
        """Init LMTPServer Class"""
        LMTPServer.__init__(self, localaddr)
        ## Set custom banner
        self.banner = "DebuggingServer using " + __version__

    def process_message(self, peer, mailfrom, rcpttos, data):
        """Do something with the gathered message"""
        inheaders = 1
        lines = data.split('\n')
        print '----------- MESSAGE DATA ------------'
        if peer:
            print "Peer: %s:%d" % peer
        print "Mail from:", mailfrom
        print "Recipients:", ','.join(rcpttos)
        print '---------- MESSAGE HEADERS ----------'
        for line in lines:
            if inheaders and not line:
                inheaders = 0
                break
            print line
        print '------------ END MESSAGE ------------'

if __name__ == '__main__':
    #server = DebuggingServer('localhost:2003')
    server = DebuggingServer('unix:/tmp/debug-lmtp')
    print server
    try:
        server.loop(30, 1)
    except KeyboardInterrupt:
        pass
