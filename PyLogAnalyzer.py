#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2
#
# Copyright (C) 2007 Gianluigi Tiesi <sherpya@netfarm.it>
# Copyright (C) 2007 NetFarm S.r.l.  [http://www.netfarm.it]
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
## @file PyLogAnalyzer.py
## Netfarm Mail Archiver [loganalyzer]

from anydbm import open as dbopen
from rfc822 import parseaddr
from mx.DateTime.Parser import DateTimeFromString
from psycopg2 import connect
import re

DBDSN = 'host=localhost dbname=mail user=archiver password=mail'

re_line   = re.compile(r'(\w+\s+\d+\s+\d+:\d+:\d+) (.*?) (.*?)\[(\d*?)\]: (.*)')
re_status = re.compile(r'to=(.*?), relay=(.*?), delay=(.*?), delays=(.*?), dsn=(.*?), status=(.*?) \((.*)\)')
re_qmgr   = re.compile(r'from=(.*?), size=(\d*?), nrcpt=(\d*?)\s')

re_relay  = { 'smtp': re.compile(r'(.*?)\[(.*?)\]:(\d+)'), 'lmtp': re.compile(r'(.*?)()\[(.*?)\]') }

re_sendmid = re.compile(r'from=(.*?), size=(\d*?), class=\d+, nrcpts=(\d*?), msgid=(.*?), proto=.*?, daemon=.*?, relay=(.*)')
re_sendstat = re.compile(r'to=(.*?), delay=(.*?),.*, relay=(.*?), dsn=(.*?), stat=(.*?)\s(.*)')

defskiplist   = [ '127.0.0.1', 'localhost' ]

E_ALWAYS = 0
E_INFO   = 1
E_WARN   = 2
E_ERR    = 3
E_TRACE  = 4

loglevel = E_ERR

dbquery = """
insert into mail_log (
    message_id,
    r_date,
    d_date,
    dsn,
    relay_host,
    relay_port,
    delay,
    status,
    status_desc,
    mailto,
    ref
) values (
    '%(message_id)s',
    '%(r_date)s',
    '%(d_date)s',
    '%(dsn)s',
    '%(relay_host)s',
    %(relay_port)s,
    %(delay)s,
    '%(status)s',
    '%(status_desc)s',
    '%(mailto)s',
    '%(ref)s'
);

"""

PyLog = None

def log(severity, text):
    if severity <= loglevel:
        print text

class PyLogAnalyzer:
    def __init__(self, filename, dbfile='cache.db', sync=True, skiplist=defskiplist):
        self.log = log
        self.skiplist = skiplist
        self.sync = sync

        try:
            self.dbConn = connect(DBDSN)
            self.dbCurr = self.dbConn.cursor()
        except:
            raise Exception, 'Cannot connect to DB'

        try:
            self.fd = open(filename, 'r')
        except:
            raise Exception, 'Cannot open log file'

        try:
            self.db = dbopen(dbfile, 'c')
        except:
            self.fd.close()
            raise Exception, 'Cannot open cache db'

    def __del__(self):
        ## FIXME log in dtor is None
        try:
            self.dbCurr.close()
            self.dbConn.close()
        except:
            self.log(E_ALWAYS, 'Error closing connection to DB')

        try:
            self.fd.close()
        except:
            self.log(E_ALWAYS, 'Error closing logfile fd')

        self.log(E_TRACE, 'Cache content: ' + str(self.db.keys()))
        try:
            self.db.close()
        except:
            self.log(E_ALWAYS, 'Error closing cache db')

        self.log(E_ALWAYS, 'Job Done')

    def insert(self, info):
        log(E_ERR, '%(message_id)s %(mailto)s [%(r_date)s --> %(d_date)s] %(ref)s %(dsn)s %(status)s %(relay_host)s:%(relay_port)s' % info)
        #log(E_TRACE, '[%(r_date)s --> %(d_date)s] %(delay)s' % info)
        return True

        qs = dbquery % info
        try:
            self.dbCurr.execute(qs)
            self.dbConn.commit()
        except:
            log(E_ERR, 'DB Query Error')
            self.dbConn.rollback()

        return True

    def delkey(self, key):
        if self.db.has_key(key):
            del self.db[key]
            if self.sync: self.db.sync()

    def addkey(self, key, value):
        self.db[key] = value
        if self.sync: self.db.sync()

    def mainLoop(self):
        while 1:
            ## Read a line
            try:
                line = self.fd.readline().strip()
            except (KeyboardInterrupt, IOError):
                break

            ## No data, exit
            if not len(line):
                log(E_ALWAYS, 'No more data, exiting')
                break

            ## Parse the line
            res = re_line.match(line)
            ## No match, continue
            if res is None:
                log(E_TRACE, 'No match on ' + line)
                continue

            ## Parse fields
            ddatestr, host, name, pid, line = res.groups()
            line = line.split(': ', 1)
            if len(line) != 2: continue
            ref, msg = line

            ## Get process/subprocess
            proc = name.split('/', 1)
            if len(proc) == 1:
                ## Single name
                process = subprocess = proc[0]
            elif len(proc) == 2:
                ## process/subprocess
                process, subprocess = proc
            else:
                ## How many slashes?
                log(E_ERR, 'Too many slashes in process name ' + name)
                continue

            ## Pick the needed parse method
            hname = '_'.join([process, subprocess])
            handler = getattr(self, hname, None)
            if handler is None:
                #log(E_TRACE, 'Process function not found, ' + hname)
                continue

            ## Map fields
            info = dict(ddatestr=ddatestr,
                        host=host,
                        pid=pid,
                        ref=ref,
                        msg=msg,
                        process=process,
                        subprocess=subprocess)

            ## TODO try/except
            res = handler(info.copy())

    ## Merge message_id and date and put them into the cache db
    def postfix_cleanup(self, info):
        mid = info['msg'].split('=', 1).pop().strip()
        ref = info['ref']
        self.addkey(ref, '|'.join([info['ddatestr'], mid]))

    ## If qmgr removes from queue then, remove
    def postfix_qmgr(self, info):
        if info['msg'].lower() == 'removed':
            ref = info.get('ref', None)
            if ref is None:
                log(E_ERR, 'qmgr no ref')
            else:
                self.delkey(ref)
#        else:
#            # from=<root@eve.netfarm.it>, size=484, nrcpt=3 (queue active)
#            res = re_qmgr.match(info['msg'])
#            if res is None: continue
#            mailfrom, size, nrcpt = res.groups()
#            try:
#                mailfrom = parseaddr(mailfrom)[1]
#            except:
#                continue


    def postfix_smtp(self, info):
        ## Check ref for validity
        ref = info['ref']

        ## Skip 'connect to' - FIXME find a better way
        if len(ref) != 11: return False

        if not self.db.has_key(ref):
            log(E_TRACE, 'No ref match in the cache, ' + ref)
            return False

        if self.db[ref].find('|') == -1:
            log(E_ERR, 'Invalid ref value in the cache ' + ref)
            return False

        ## Split and parse the msg
        msg = info['msg']
        res = re_status.match(msg)

        if res is None:
            log(E_ERR, 'Cannot parse message, ' + msg)
            return False

        ## Get important infos
        mailto, relay, delay, delays, dsn, status, msg = res.groups()

        ## Sanitize
        status = status.lower().strip()
        dsn = dsn.strip()
        msg = msg.strip().replace('\n', '')

        ## Parse delay float
        try:
            delay = float(delay)
        except:
            delay = 0.0

        ## Parse mailto with rfc822 module
        try:
            mailto = parseaddr(mailto)[1]
        except:
            log(E_ERR, 'Error while parsing mailto address, ' + mailto)
            return False

        ## Parse delivery date
        ddatestr = info['ddatestr']
        try:
            d_date = DateTimeFromString(ddatestr)
        except:
            log(E_ERR, 'Error parsing sent date string, ' + ddatestr)
            return False

        ## Parse received date
        rdatestr, mid = self.db[ref].split('|', 1)
        try:
            r_date = DateTimeFromString(rdatestr)
        except:
            log(E_ERR, 'Error parsing received date string, ' + rdatestr)
            return False

        ## Maybe deferred, relay is none
        if relay == 'none':
            relay_host = 'none'
            relay_port = 0
        else:
            res = re_relay[info['subprocess']].match(relay)
            if res is None:
                log(E_ERR, 'Cannot parse relay address, ' + relay)
                return False

            ## Parse relay string
            relay = res.groups()

            ## Stop if we don't need the log
            if relay[0] in self.skiplist:
                return True

            ### FIXME lmtp
            relay_host = relay[0].strip()
            try:
                relay_port = int(relay[2].strip())
            except:
                relay_port = 25

        d = dict(message_id=mid, r_date=r_date.Format(), d_date=d_date.Format(),
                 dsn=dsn,
                 relay_host=relay_host,
                 relay_port=relay_port,
                 delay=delay,
                 status=status,
                 status_desc=msg[:512],
                 mailto=mailto,
                 ref=ref)

        info.update(d)
        return self.insert(info)

    #postfix_lmtp = postfix_smtp
    def postfix_lmtp(self, info):
        return True

    def sendmail_sendmail(self, info):
        msg = info['msg']
        ref = info['ref']
        if msg.startswith('from=') and (msg.find('msgid=') != -1):
            res = re_sendmid.match(msg)
            if res is None: return True # no msgid line
            mailfrom, size, nrcpts, mid, relay = res.groups()
            if mailfrom == '<>': return True # no return path
            self.addkey(ref, '|'.join([info['ddatestr'], mid]))
        elif msg.startswith('to='):
            res = re_sendstat.match(msg)
            if res is None: # not parsable
                # remove the reference
                self.delkey(ref)
                return True

            ## TODO: parse mailto, understand delay value
            mailto, delay, relay, dsn, status, msg = res.groups()

            if not self.db.has_key(ref): return False
            rdatestr, mid = self.db[ref].split('|', 1)
            self.delkey(ref) # remove reference in cache

            relay_host = relay ## TODO: parse
            relay_port = 25

            ## Parse delivery date
            ddatestr = info['ddatestr']
            try:
                d_date = DateTimeFromString(ddatestr)
            except:
                log(E_ERR, 'Error parsing sent date string, ' + ddatestr)
                return False

            ## Parse received date
            try:
                r_date = DateTimeFromString(rdatestr)
            except:
                log(E_ERR, 'Error parsing received date string, ' + rdatestr)
                return False

            d = dict(message_id=mid, r_date=r_date.Format(), d_date=d_date.Format(),
                 dsn=dsn,
                 relay_host=relay_host,
                 relay_port=relay_port,
                 delay=delay,
                 status=status.lower(),
                 status_desc=msg[:512],
                 mailto=mailto,
                 ref=ref)
            info.update(d)
            return self.insert(info)
        elif msg.startswith('SYSERR') or msg.startswith('timeout'): ## FIXME: a better way
            self.delkey(ref)
        else:
            pass # ignored


def sigtermHandler(signum, frame):
    log(E_ALWAYS, 'SiGTERM received')

if __name__ == '__main__':
    from sys import argv, exit as sys_exit
    from signal import signal, SIGTERM

    if len(argv) != 2:
        print 'Usage %s logfile|fifo' % argv[0]
        sys_exit()

    signal(SIGTERM, sigtermHandler)
    PyLog = PyLogAnalyzer(argv[1])
    PyLog.mainLoop()
