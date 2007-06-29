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
from sys import exit as sys_exit
from signal import signal, SIGTERM
import re

DBDSN = 'host=localhost dbname=mail user=archiver password=mail'

re_line   = re.compile(r'(\w\w\w \d\d \d\d:\d\d:\d\d) (.*?) (.*?)\[(\d*?)\]: (.*)')
re_status = re.compile(r'to=(.*?), relay=(.*?), delay=(.*?), delays=(.*?), dsn=(.*?), status=(.*?) \((.*)\)')
re_qmgr   = re.compile(r'from=(.*?), size=(\d*?), nrcpt=(\d*?)\s')

re_relay  = { 'smtp': re.compile(r'(.*?)\[(.*?)\]:(\d+)'), 'lmtp': re.compile(r'(.*?)()\[(.*?)\]') }

defskiplist   = [ '127.0.0.1', 'localhost' ]

E_ALWAYS = 0
E_INFO   = 1
E_WARN   = 2
E_ERR    = 3
E_TRACE  = 4

loglevel = E_ALWAYS

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

supported = [ 'postfix' ]

PyLog = None

def log(severity, text):
    if severity <= loglevel:
        print text

class PyLogAnalyzer:
    def __init__(self, filename, dbfile='cache.db', rule='postfix', skiplist=defskiplist):
        self.fd = open(filename, 'r')
        self.db = dbopen(dbfile, 'c')
        if rule not in supported:
            raise Exception, 'Rule not supported'
        self.rule = rule
        self.skiplist = skiplist
        self.log = log

    def __del__(self):
        ## FIXME log in dtor it's not defined
        try:
            self.fd.close()
        except:
            self.log(E_ALWAYS, 'Error closing logfile fd')

        try:
            self.db.close()
        except:
            self.log(E_ALWAYS, 'Error closing cache db')

        self.log(E_ALWAYS, 'exiting by user request')

    def insert(self, info):
        #qs = query % info
        out = '%(message_id)s %(mailto)s [%(r_date)s --> %(d_date)s] %(ref)s %(dsn)s %(status)s %(relay_host)s:%(relay_port)s' % info
        log(E_ALWAYS, out)
        return True

    def mainLoop(self):
        while 1:
            ## Read a line
            try:
                line = self.fd.readline().strip()
            except KeyboardInterrupt:
                break
            except IOError:
                break

            ## No data, exit
            if not len(line):
                log(E_ALWAYS, 'No more data, exiting')
                break

            ## Parse the line
            res = re_line.match(line)
            ## No match, continue
            if res is None:
                log(E_ERR, 'No match, skipping line')
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
            cbname = '_'.join([self.rule, subprocess])
            cb = getattr(self, cbname, None)
            if cb is None:
                #log(E_TRACE, 'Process function not found, ' + cbname)
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
            res = cb(info.copy())

    ## Merge message_id and date and put them into the cache db
    def postfix_cleanup(self, info):
        mid = info['msg'].split('=', 1).pop().strip()
        self.db[info['ref']] = '|'.join([info['ddatestr'], mid])
        self.db.sync()

    ## If qmgr removes from queue then, remove
    def postfix_qmgr(self, info):
        if info['msg'].lower() == 'removed':
            ref = info['ref']
            log(E_TRACE, 'qmgr removed ' + ref)
            del self.db[ref]
            self.db.sync()
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
        if not self.db.has_key(ref):
            log(E_ERR, 'No ref match in the cache, ' + ref)
            return False

        if self.db[ref].find('|') == -1:
            print ref
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

    postfix_lmtp = postfix_smtp

def sigtermHandler(signum, frame):
    log(E_ALWAYS, 'SiGINT received')

if __name__ == '__main__':
    signal(SIGTERM, sigtermHandler)
    PyLog = PyLogAnalyzer('/var/log/mail.log')
    PyLog.mainLoop()
