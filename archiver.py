#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2
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
## @file archiver.py
## Netfarm Mail Archiver [core]

__doc__ = '''Netfarm Archiver relase 2.0.0 - Main worker'''
__version__ = '2.0.0'
__all__ = [ 'BackendBase',
            'StorageTypeNotSupported',
            'BACKEND_OK',
            'mime_decode_header',
            'E_NONE',
            'E_ERR',
            'E_INFO',
            'E_TRACE',
            'E_ALWAYS',
            'platform' ] # import once

from sys import platform
if platform == 'win32':
    from win32api import GetCurrentProcessId
else:
    from signal import signal, SIGTERM, SIGINT, SIGHUP, SIG_IGN
    from os import fork, kill, seteuid, setegid, getuid
    from pwd import getpwnam, getpwuid
from lmtp import LMTPServer, SMTPServer, LMTP, SMTP
from time import strftime, time, localtime, sleep, mktime
from sys import argv, exc_info, stdin, stdout, stderr
from sys import exit as sys_exit
from os import getpid, unlink, chmod, access, F_OK, R_OK
from os import close, dup
from anydbm import open as opendb
from mimetools import Message
from multifile import MultiFile
from rfc822 import parseaddr
from smtplib import SMTP
from ConfigParser import ConfigParser
from mimify import mime_decode
from base64 import decodestring
from threading import Thread, RLock
from cStringIO import StringIO
from getopt import getopt

import re

### Debug levels
E_NONE=0
E_ERR=1
E_INFO=2
E_TRACE=3
E_ALWAYS=-1
DEBUGLEVELS = { 'none'  : E_NONE,
                'error' : E_ERR,
                'info'  : E_INFO,
                'trace' : E_TRACE,
                'always': E_ALWAYS }
### Usefull constants
NL='\n'
AID='X-Archiver-ID'
STARTOFBODY=NL+NL
GRANULARITY=10
BACKEND_OK = (1, 200, 'Ok')
MINSIZE=8

### Globals
LOG = None
config = None
quotatbl = None
isRunning = 0
main_svc = 0
serverPoll = []
##
class DEBUGServer:
    """Debug Server used only for debugging connections"""
    def __init__(self, address, port):
        """DEBUGServer Constructor"""
        print 'DEBUGServer: output %s:%s' % (address, port)

    def sendmail(self, m_from, m_to, msg):
        """DEBUGServer fake sendmail"""
        print 'DEBUGServer: sendmail from: %s to %s - size %d' % (m_from, m_to, len(msg))
        return ''  
        
    def close(self):
        """DEBUGServer dummy close"""
        pass
    
re_aid = re.compile(r'^(X-Archiver-ID: .*?)[\r|\n]', re.IGNORECASE | re.MULTILINE)
CHECKHEADERS = ['from', 'to', 'cc', 'subject', 'date', 'message-id', AID.lower()]
whitelist = []
input_classes  = { 'lmtp': LMTPServer, 'smtp': SMTPServer }
output_classes = { 'lmtp': LMTP, 'smtp': SMTP, 'debug': DEBUGServer }

class StorageTypeNotSupported(Exception):
    """StorageTypeNotSupported The storage type is not supported"""
    pass

class BadStageTypeError(Exception):
    """BadStageTypeError The Stage type is wrong"""
    pass

class BadStageInput(Exception):
    """BadStageInput The Input Stage is wrong"""
    pass

class BadStageOutput(Exception):
    """BadStageOutput The Output Stage is wrong"""
    pass

class BadBackendTypeError(Exception):
    """BadBackendTypeError An error occurred when importing Backend module"""
    pass

class BackendBase:
    """BackendBase Class

        This class should be derived to make a specialized Backend class"""
    
    def process(self, data):
        """method to process data

        should be implemented when subclassing"""
        del data
        return 0, 433, 'Backend not configured'
        
    def shutdown(self):
        """method to shudown and cleanup the backend

        should be implemented when subclassing"""
        pass

class DebugBackend(BackendBase):
    """A fake Backend

    used only to debug the process"""
    def process(self, data):
        LOG(E_INFO, "[DebugBackend]: %s" % str(data))
        return 1234, 250, 'Ok'

    def shutdown(self): pass
                 
class Logger:
    """Message Logger class

    Used to log message to a file"""
    def __init__(self, debug=None):
        """The constructor"""
        global config
        if debug:
            self.log_fd = stdout
        else:
            try:
                self.log_fd = open(config.get('global', 'logfile'), 'a')
            except:
                print 'Cannot open logfile, using stderr'
                self.log_fd = stderr

        try:
            self.loglevel = DEBUGLEVELS[config.get('global', 'loglevel').lower()]
        except:
            print 'Bad log level defined'
            self.loglevel = E_ERR 
        
        try:
            self.logstrtime = config.get('global', 'logstrtime')
        except:
            self.logstrtime = "%m/%d/%Y %H:%M:%S"

    def __call__(self, level, msg):
        """Default call method for Logger class

        It's used to append a message to the logfile depending on
        the severity"""
        if self.loglevel < level:
            return
        timestr = strftime(self.logstrtime, localtime(time()))
        outstr = "%s %s\n" % (timestr, msg)
        try:
            self.log_fd.write(outstr)
            self.log_fd.flush()
        except:
            pass
        del timestr, outstr

    def fileno(self):
        """returns logfile fd

        Used to pass it on some backends like xmlrpc"""
        return self.log_fd.fileno()

    def flush(self):
        """flushes the Logger fd to force the write operation"""
        return self.log_fd.flush()
    
    def close(self):
        """closes the Logger fd"""
        try:
            self.log_fd.close()
        except: pass

### Helpers
mime_head = re.compile('=\\?(.*?)\\?(\w)\\?([^? \t\n]+)\\?=', re.IGNORECASE)
encodings = {'q': mime_decode, 'b': decodestring }


def mime_decode_header(line):
    """workaound to python mime_decode_header

    The original code doesn't support base64"""
    newline = ''
    pos = 0
    while 1:
        res = mime_head.search(line, pos)
        if res is None:
            break
        #charset = res.group(1)
        enctype = res.group(2).lower()
        match = res.group(3)
        if encodings.has_key(enctype):
            match = ' '.join(match.split('_'))
            newline = newline + line[pos:res.start(0)] + encodings[enctype](match)
        else:
            newline = newline + line[pos:res.start(0)] + match
        pos = res.end(0)

    return newline + line[pos:]

def split_hdr(key, ct_string, dict):
    """Headers splitting

    extract file name and content-disposition"""
    if ct_string.find(';') != -1:
        dict[key], params = ct_string.split(';', 1)
        params = params.strip().split(';')
        for par in params:
            par = par.strip()
            if par.find('=') != -1:
                pname, pvalue = par.split('=', 1)
                pname = pname.strip()
                pvalue = pvalue.strip()
                if pvalue[0] == '"' and pvalue[-1] == '"' and pvalue !='""':
                    pvalue = pvalue[1:-1]
                dict[pname] = pvalue
    else:
        dict[key] = ct_string


def parse(submsg):
    """Parse a sub message"""
    found = None
    if submsg.dict.has_key('content-type'):
        ct = submsg.dict['content-type']
        dict = {}
        split_hdr('Content-Type', ct, dict)
        
        if submsg.dict.has_key('content-disposition'):
            cd = submsg.dict['content-disposition']
            split_hdr('Content-Disposition', cd, dict)

        ### Hmm nice clients, filename or name?
        if not dict.has_key('name') and dict.has_key('filename'):
            dict['name'] = dict['filename']

        ### Found an attachment
        if dict.has_key('name'):
            LOG(E_TRACE, 'Found attachment: ' + dict['name'] + ' - Enctype: ' + submsg.getencoding())
            found = { 'name': dict['name'], 'content-type': dict['Content-Type'] }
    return found

def dupe_check(headers):
    """Check for duplicate headers

    Some headers should be unique"""
    check = []
    for hdr in headers:
        hdr = hdr.strip()
        if hdr.find(':')==-1: continue
        key, value = hdr.split(':', 1)
        key = key.lower()
        if key in check and key in CHECKHEADERS:
            return 1
        check.append(key)
    return 0

def StageHandler(config, stage_type):
    """Meta class for a StageHandler Backend"""
##### Class Wrapper - Start
    ### I need class type before __init__
    try:
        input_class = config.get(stage_type, 'input').split(':', 1)[0]
        if not input_classes.has_key(input_class):
            raise BadStageInput, input_class
    except:
        raise BadStageInput
        
    class StageHandler(Thread, input_classes[input_class]):
        """Base class for a StageHandler Backend"""
        def __init__(self, Class, config, stage_type):
            """StageHandler Constructor"""
            global main_svc
            self.process_message = getattr(self, 'process_' + stage_type, None)
            if self.process_message is None:
                raise BadStageTypeError, stage_type

            try:
                self.proto, self.address = config.get(stage_type, 'input').split(':', 1)
            except:
                raise BadStageInput

            Thread.__init__(self)
            ## Init LMTPServer Class
            Class.__init__(self, self.address, self.del_hook)
            self.lock = RLock()
            self.type = stage_type
            
            ## Setup handle_accept Hook
            self._handle_accept = self.handle_accept
            self.handle_accept = self.accept_hook

            try:
                self.usepoll = config.getint('global', 'usepoll')
            except:
                self.usepoll = 1
            try:
                self.granularity = config.getint('global', 'granularity')
            except:
                self.granularity = GRANULARITY

            ## Win32 Fixups
            if platform == 'win32':
                ## No support for poll on win32
                self.usepoll = 0 
                ## Bug: hang on close if using psycopg / Not needed if run as service
                self.setDaemon(main_svc)
                
            try:
                self.nowait = config.getint('global', 'nowait')
            except:
                self.nowait = 0

            try:
                self.timeout = config.getint('global', 'timeout')
            except:
                self.timeout = None
            
            ## Init Hashdb to avoid re-archiving
            try:
                self.hashdb = opendb(config.get(self.type, 'hashdb'), 'c')
            except:
                LOG(E_TRACE, '%s: Cannot open hashdb file' % self.type)
                raise Exception, '%s: Cannot open hashdb file' % self.type

            try:
                self.debuglevel = config.getint(self.type, 'debuglevel')
            except:
                self.debuglevel = 0
            
            ## Set custom banner
            self.banner = 'Netfarm Archiver [%s] version %s' % (stage_type, __version__)
            
            try:
                output, address = config.get(stage_type, 'output').split(':', 1)
                if not output_classes.has_key(output):
                    raise BadStageOutput, output
            except:
                raise BadStageOutput

            self.output = output_classes[output]
            try:
                self.output_address, self.output_port = address.split(':', 1)
                self.output_port = int(self.output_port)
            except:
                raise BadStageOutput, self.output
                        
            ## Backend factory
            self.config = config
            backend_type = self.config.get(stage_type, 'backend')
            try:
                backend = getattr(__import__("backend_%s" % backend_type, globals(), locals(), []), 'Backend')
            except ImportError:
                t, val, tb = exc_info()
                del tb
                LOG(E_ERR, '%s: Cannot import backend: %s' % (self.type, str(val)))
                raise BadBackendTypeError, str(val)

            self.backend = backend(self.config, stage_type, globals())
            self.shutdown_backend = self.backend.shutdown

        def run(self):
            self.setName(self.type)
            LOG(E_ALWAYS, '[%d] Starting Stage Handler %s: %s %s' % (getpid(), self.type, self.proto, self.address))
            self.loop(self.granularity, self.usepoll, self.map)

        ## Hooks to gracefully stop threads
        def accept_hook(self):
            """hook called when the server accepts an incoming connection"""
            LOG(E_TRACE, '%s: I got a connection: Acquiring lock' % self.type)
            self.lock.acquire()
            return self._handle_accept()

        def del_hook(self):
            """hook called when a connection is terminated"""
            LOG(E_TRACE, '%s: Connection closed: Releasing lock' % self.type)
            self.lock.release()

        def finish(self, force=0):
            """shutdown the Archiver system waiting for unterminated jobs"""
            if not self.nowait and not force:
                LOG(E_TRACE, '%s: Waiting thread job...' % self.getName())
                self.lock.acquire()
                LOG(E_TRACE, '%s: Done' % self.getName())
            self.close_all()
                        
        def sendmail(self, m_from, m_to, msg, aid=None, mid=None):
            """Rerouting of mails to nexthop (postfix)"""
            
            if msg is None: # E.g. regex has failed
                LOG(E_ERR, '%s-sendmail: msg is None something went wrong ;(' % self.type)
                return self.do_exit(443, 'Internal server error')
            
            try:
                server = self.output(self.output_address, self.output_port)
            except:
                t, val, tb = exc_info()
                del tb
                LOG(E_ERR, '%s-sendmail: Failed to connect to output server: %s' % (self.type, str(val)))
                return self.do_exit(443, 'Failed to connect to output server')

            ## Null path - smtplib doesn't enclose '' in brackets
            if m_from == '':
                m_from = '<>'

            server_reply = {}                    

            ## Here python developers was very funny, if a mail is not delivered to one of recipients
            ## then I have bad recipient list in the return value
            ## If the recipient is only one and mail is not delivered
            ## (maybe also if many recipients are bad recipients)
            ## bad recipient list is in traceback, really funny ;)
            try:
                server_reply = server.sendmail(m_from, m_to, msg)
            except:
                t, server_reply, tb = exc_info()
                server_reply = server_reply[0]

            try:
                server.close()
            except: pass

            ## We can get a dict or an integer
            if type(server_reply) == type(0):
                server_reply = str(server_reply)
                
            if len(server_reply) == 0:
                okmsg = 'Sendmail Ok'
                if aid:
                    okmsg = 'Archived as: ' + aid

                if mid is not None and self.hashdb.has_key(mid):
                    LOG(E_TRACE, '%s-sendmail: expunging msg %s from hashdb' % (self.type, aid))
                    del self.hashdb[mid]
                    self.hashdb.sync()

                return self.do_exit(250, okmsg, 200)
            else:
                if type(server_reply)==type({}):
                    for rcpt in server_reply.keys():
                        res = server_reply[rcpt]
                        LOG(E_ERR, '%s-sendmail error: %s - %s' % (self.type, res[0], res[1]))
                elif type(server_reply)==type(''):
                    LOG(E_ERR, '%s-sendmail reply error, server returned error code %s' % (self.type, server_reply))
                    return self.do_exit(443, 'Server returned code ' + server_reply)
                else:
                    LOG(E_ERR, '%s-sendmail unknown error: %s' % (self.type, str(server_reply)))
                    return self.do_exit(443, 'Internal server error')
                
                ## TODO 2.x - find the right way
                if len(server_reply) == len(m_to):
                    return self.do_exit(443, 'All recipients were rejected by the mailserver')

                LOG(E_TRACE, '%s-sendmail: expunging msg %s from hashdb' % (self.type, aid))
                ## TODO 2.x - It's ok to do this??
                del self.hashdb[mid]
                self.hashdb.sync()
                return self.do_exit(200, 'Some of recipients were rejected by the mailserver')

        def do_exit(self, code, msg='', extcode=None):
            """Exit function

            @returns: exit code and messages"""
            self.del_channel()
            if not extcode:
                extcode = code
            excode =  '.'.join([x for x in str(extcode)])
            return ' '.join([str(code), excode, msg])

        def process_storage(self, peer, sender, recips, data):
            """Stores the archived email using a Backend"""
            size = len(data)
            if size < MINSIZE:
                return self.do_exit(550, 'Invalid Mail')
            
            stream = StringIO(data)
            msg = Message(stream)
            aid = msg.get(AID, None)

            ## Check if I have msgid in my cache
            mid = msg.get('message-id', '')
            LOG(E_TRACE, '%s: Message-id: %s' % (self.type, mid))
            if self.hashdb.has_key(mid):
                aid=self.hashdb[mid]
                LOG(E_ERR, '%s: Message has yet been processed' % self.type)
                return self.sendmail(sender, recips, data, aid, mid)

            m_date = msg.getdate('Date')
            try:
                mktime(m_date)
            except:
                m_date = None
                            
            if m_date is None:
                LOG(E_ERR, '%s: Invalid date format using current time' % self.type)
                m_date = localtime(time())
                        
            del msg,stream

            ## Mail needs to be processed
            if aid:
                try:
                    year, pid = aid.split('-', 1)
                    year = int(year)
                    pid = int(pid)
                except:
                    t, val, tb = exc_info()
                    del tb
                    LOG(E_ERR, '%s: Invalid X-Archiver-ID header [%s]' % (self.type, str(val)))
                    return self.do_exit(550, 'Invalid X-Archiver-ID header')

                stuff = { 'mail': data, 'year': year, 'pid': pid, 'date': m_date }
                LOG(E_TRACE, '%s: year is %d - pid is %d' % (self.type, year, pid))
                status, code, msg = self.backend.process(stuff)
                if status==0:
                    LOG(E_ERR, '%s: process failed %s' % (self.type, msg))
                    return self.do_exit(code, msg)

                ## Inserting in hashdb
                LOG(E_TRACE, '%s: inserting %s msg in hashdb' % (self.type, aid))
                self.hashdb[mid]=aid
                self.hashdb.sync()
                LOG(E_TRACE, '%s: backend worked fine' % self.type)
            else:
                ## Mail in whitelist - not processed
                LOG(E_TRACE, '%s: X-Archiver-ID header not found in mail [whitelist]' % self.type)
            ## Next hop
            LOG(E_TRACE, '%s: passing data to nexthop: %s:%s' % (self.type, self.output_address, self.output_port))
            return self.sendmail(sender, recips, data, aid, mid)

        def add_aid(self, data, msg, aid):
            archiverid = '%s: %s' % (AID, aid)
            LOG(E_INFO, '%s: %s' % (self.type, archiverid))
            archiverid = archiverid + NL
            headers = data[:msg.startofbody]
            if msg.get(AID, None):
                LOG(E_ERR, '%s: Warning overwriting X-Archiver-ID header' % self.type)
                ## Overwrite existing header
                try:
                    data = re_aid.sub(archiverid, headers, 1).strip() + STARTOFBODY + data[msg.startofbody:]
                except:
                    t, val, tb = exc_info()
                    del tb
                    LOG(E_ERR, '%: Error overwriting X-Archiver-ID header: %s' % (self.type, str(val)))
                    return None
            else:
                data = headers.strip() + NL + archiverid + STARTOFBODY + data[msg.startofbody:]

            return data

        def remove_aid(self, data, msg):
            if msg.get(AID, None):
                LOG(E_ERR, '%s: This mail should not have X-Archiver-ID header, removing it' % self.type)
                try:
                    headers = data[:msg.startofbody]
                    data = re_aid.sub('', headers, 1).strip() + STARTOFBODY + data[msg.startofbody:]
                except:
                    t, val, tb = exc_info()
                    del tb
                    LOG(E_ERR, '%s: Error removing X-Archiver-ID header: %s' % (self.type, str(val)))
            return data
        
        def process_archive(self, peer, sender, recips, data):
            """Archives email meta data using a Backend"""
            global quotatbl
            global whitelist

            LOG(E_INFO, '%s: Sender is <%s> - Recipients (Envelope): %s' % (self.type, sender, ','.join(recips)))
            
            size = len(data)
            if size < MINSIZE:
                return self.do_exit(550, 'Invalid Mail')

            stream = StringIO(data)
            msg = Message(stream)

            if sender == '':
                LOG(E_INFO, '%s: Null return path mail, not archived' % (self.type))
                return self.sendmail('<>', recips, self.remove_aid(data, msg))

            ## Check if I have msgid in my cache
            mid = msg.get('message-id', None)
            if mid is not None and self.hashdb.has_key(mid):
                LOG(E_TRACE, '%s: Message-id: %s' % (self.type, mid))
                aid=self.hashdb[mid]
                LOG(E_ERR, '%s: Message has yet assigned year/pid pair, only adding header' % self.type)
                return self.sendmail(sender, recips, self.add_aid(data, msg, aid), aid, mid)

            ## Check for duplicate headers
            if dupe_check(msg.headers):
                LOG(E_ERR, '%s: Invalid syntax in headers' % self.type)
                return self.do_exit(552, 'Invalid Syntax in headers')

            ## Extraction of from field
            m_from = msg.getaddrlist('From')

            ## Extraction of to field
            m_to = msg.getaddrlist('To')
            
            ## whitelist check, from, to and sender (envelope)
            try:
                check_sender = [parseaddr(sender)]
            except:
                LOG(E_ERR, '%s: cannot parse %s' % (self.type, sender))
                check_sender = []
                            
            for addr in m_from+m_to+check_sender:
                try:
                    base = addr[1].split('@')[0]
                except:
                    base = addr
                LOG(E_TRACE, 'whitelist check: %s' % base)
                if base in whitelist:
                    LOG(E_INFO, '%s: Mail to: %s in whitelist, not archived' % (self.type, base))
                    return self.sendmail(sender, recips, self.remove_aid(data, msg))

            ## Size check
            ## TODO 2.x check if it works
            if quotatbl:
                for addr in m_from:
                    try:
                        checkfrom = addr[1].split('@')[0]
                    except:
                        checkfrom = addr
                    LOG(E_TRACE, '%s: Checking quota for %s' % (self.type, checkfrom))
                    size = size >> 10

                    try:
                        csize = int(quotatbl[checkfrom])
                    except:
                        csize = 0

                    if csize and size > csize:
                        LOG(E_ERR, '%s: Send quota execeded from: %s' % (self.type, checkfrom))
                        return self.do_exit(523, 'Send quota execeded')

            ## Extraction of cc field
            m_cc = msg.getaddrlist('Cc')

            ## Extraction of Subject field
            m_sub = msg.get('Subject', '')

            ## Date extraction
            m_date = msg.getdate('Date')
            try:
                mktime(m_date)
            except:
                m_date = None
                
            if m_date is None:
                LOG(E_ERR, '%s: Invalid date format using current time' % self.type)
                m_date = localtime(time())
            
            m_attach = []

            ## If multipart sould be attachment (but not always)
            if msg.maintype != 'multipart':
                m_parse = parse(msg)
                if m_parse is not None:
                    m_attach.append(m_parse)
            else:
                file = MultiFile(stream)
                file.push(msg.getparam('boundary'))
                try:
                    while file.next():
                        submsg = Message(file)
                        subpart = parse(submsg)
                        if subpart is not None:
                            m_attach.append(subpart)
                except:
                    LOG(E_ERR, '%s: Error in multipart splitting' % self.type)

            dict = {}
            dict['m_from'] = m_from
            dict['m_to'] = m_to
            dict['m_cc'] = m_cc
            dict['m_sub'] = m_sub
            dict['m_date'] = m_date
            dict['m_attach'] = m_attach

            year, pid, error = self.backend.process(dict)
            if year==0:
                LOG(E_ERR, '%s: Backend Error: %s' % (self.type, error))
                return self.do_exit(pid, error)
                
            ## Adding X-Archiver-ID: header
            aid = '%d-%d' % (year, pid)
            data = self.add_aid(data, msg, aid)
            if mid is not None:
                LOG(E_TRACE, '%s: inserting %s msg in hashdb' % (self.type, aid))
                self.hashdb[mid]=aid
                self.hashdb.sync()
            ## Next hop
            LOG(E_TRACE, '%s: backend worked fine' % self.type)
            LOG(E_TRACE, '%s: passing data to nexthop: %s:%s' % (self.type, self.output_address, self.output_port))
            return self.sendmail(sender, recips, data, aid, mid)
##### Class Wrapper - End
    return apply(StageHandler, (input_classes[input_class], config, stage_type))

def multiplex(objs, function, *args):
    """Generic method multiplexer

    It executes the given method and args for each object in the list"""
    res = []
    for obj in objs:
        method = getattr(obj, function, None)
        if method: res.append(apply(method, args))
    return res

def sig_int_term(signum, frame):
    """Handler for SIGINT and SIGTERM signals

    Terminates the StageHandler threads"""
    global isRunning
    del signum, frame
    LOG(E_ALWAYS, "[Main] Got SIGINT/SIGTERM")
    isRunning = 0
    
    if len(serverPoll):
        LOG(E_ALWAYS, '[Main] Shutting down stages')
        multiplex(serverPoll, 'finish')
        multiplex(serverPoll, 'shutdown_backend')
        multiplex(serverPoll, 'stop')

def do_shutdown(res=0):
    """Archiver system shutdown"""
    global quotatbl, main_svc

    ## Close quota hash handler
    if quotatbl:
        quotatbl.close()

    if platform != 'win32':
        try:
            unlink(config.get('global', 'pidfile'))
        except: pass

    LOG(E_ALWAYS, '[Main] Waiting for child threads')
    multiplex(serverPoll, 'close')
    LOG(E_ALWAYS, '[Main] Shutdown complete')
    LOG.close()
    if main_svc:
        sys_exit(res)
    else:
        return res

## Specific Startup on unix
def unix_startup(config, user=None):
    global LOG        
    if user:
        try:
            userpw = getpwnam(user)
            setegid(userpw[3])
            seteuid(userpw[2])
        except:
            t, val, tb = exc_info()
            del t
            print 'Cannot swith to user', user, str(val)
            sys_exit(-2)
    else:
        user = getpwuid(getuid())[0]

    try:
        pidfile = config.get('global', 'pidfile')
    except:
        LOG(E_ALWAYS, '[Main] Missing pidfile in config')
        do_shutdown(-4)
        
    locked = 1
    try:        
        pid = int(open(pidfile).read().strip())
        LOG(E_TRACE, '[Main] Lock: Sending signal to the process')
        try:
            kill(pid,0)
            LOG(E_ERR, '[Main] Stale Lockfile: Process is alive')
        except:
            LOG(E_ERR, '[Main] Stale Lockfile: Old process is not alive')
            locked = 0    
    except:
        locked = 0

    if locked:
        LOG(E_ALWAYS, '[Main] Unable to start Netfarm Archiver, another instance is running')
        do_shutdown(-5)

    ## Daemonize - TODO win32 make it a service
    if not debug:
        try:
            pid = fork()
        except:
            t, val, tb = exc_info()
            del t                           
            print 'Cannot go in background mode', str(val)

        if pid: sys_exit(0)
        
        null = open('/dev/null', 'r')
        close(stdin.fileno())
        dup(null.fileno())
        null.close()
        close(stdout.fileno())
        dup(LOG.fileno())
        close(stderr.fileno())
        dup(LOG.fileno())

    ## Save my process id to file
    mypid = str(getpid())
    try:
        open(pidfile,'w').write(mypid)
    except:
        LOG(E_ALWAYS, '[Main] Pidfile is not writable')
        do_shutdown(-6)

    return user, mypid

## Specific Startup on win32
def win32_startup(config, user=None):
    return 'Windows User', GetCurrentProcessId()

## Start the Archiver Service    
def ServiceStartup(configfile, user=None, debug=None, service_main=0):
    global LOG, config, isRunning, main_svc
    main_svc = service_main
    if not access(configfile, F_OK | R_OK):
        print 'Cannot read configuration file', configfile
        return -3

    config = ConfigParser()
    config.read(configfile)

    LOG = Logger(debug=debug)
    
    if platform == 'win32':
        user, mypid = win32_startup(config)
    else:
        user, mypid = unix_startup(config, user=user)

    ## Quota table
    try:
        quotatbl = opendb(config.get('global', 'quotafile'), 'r')
        LOG(E_TRACE, '[Main] Quotacheck is enabled')
    except:
        quotatbl = None

    ## Whitelist
    try:
        whitelist = config.get('global','whitelist').split(',')
        LOG(E_TRACE, '[Main] My whitelist is ' + ','.join(whitelist))
    except:
        pass

    ## Starting up
    LOG(E_INFO, '[Main] Running as user %s pid %s' % (user, mypid))
    
    ## Creating stage sockets
    sections = config.sections()
    if 'archive' in sections:
        serverPoll.append(StageHandler(config, 'archive'))
    if 'storage' in sections:
        serverPoll.append(StageHandler(config, 'storage'))
    
    if len(serverPoll):
        multiplex(serverPoll, 'start')       
        isRunning = 1
    else:
        LOG(E_ALWAYS, '[Main] No stages configured, Aborting...')
        return do_shutdown(-7)

    try:
        granularity = config.getint('global', 'granularity')
    except:
        granularity = GRANULARITY

    ## Install Signal handlers
    if platform != 'win32':
        LOG(E_TRACE, '[Main] Installing signal handlers')
        signal(SIGINT,  sig_int_term)
        signal(SIGTERM, sig_int_term)
        signal(SIGHUP,  SIG_IGN)

    while isRunning:
        try:
            multiplex(serverPoll, 'join', granularity)
        except:
            ## Program Termination when sigint is not catched (mainly on win32)
            sig_int_term(0, 0)

    ## Shutdown
    return do_shutdown(0)

## Main
if __name__ == '__main__':  
    if platform == 'win32':
        configfile = 'archiver.ini'
        arglist = 'dc:'
    else:
        configfile='/etc/archiver.conf'
        arglist = 'dc:u:'

    try:
        optlist, args = getopt(argv[1:], arglist)
        if len(args)>0:
            raise Exception
    except:
        usage = 'Usage [%s] [-d] [-c alternate_config]' % argv[0]
        if platform != 'win32':
            usage = usage + ' [-u user]'
        print usage
        sys_exit(-1)

    debug=None
    user=None
    
    for arg in optlist:
        if arg[0] == '-c':
            configfile = arg[1]
            continue
        if arg[0] == '-d':
            debug=1
            continue
        if arg[0] == '-u':
            user=arg[1]
            continue

    ServiceStartup(configfile, user, debug, 1)