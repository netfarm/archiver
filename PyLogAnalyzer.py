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

from sys import exc_info
from anydbm import open as dbopen
from rfc822 import parseaddr
from mx.DateTime.Parser import DateTimeFromString
from psycopg2 import connect
import re

DBDSN = 'host=localhost dbname=mail user=archiver password=mail'

re_line = re.compile(r'(\w+\s+\d+\s+\d+:\d+:\d+) (.*?) (.*?)\[(\d*?)\]: (.*)')
re_msg  = re.compile(r'(\w+=.*?),')

defskiplist = [ 'none', '127.0.0.1', 'localhost' ]

E_ALWAYS = 0
E_INFO   = 1
E_WARN   = 2
E_ERR    = 3
E_TRACE  = 4

loglevel = E_ERR

queries = { 'mta':  """
insert into mail_log (
    message_id,
    r_date,
    d_date,
    dsn,
    relay,
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
    '%(relay)s',
    %(delay)s,
    '%(status)s',
    '%(status_desc)s',
    '%(mailto)s',
    '%(ref)s'
);

""" }

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

    def insert(self, mode, info):
        #log(E_ERR, '%(message_id)s %(mailto)s [%(r_date)s --> %(d_date)s] %(ref)s %(dsn)s %(status)s %(relay_host)s:%(relay_port)s' % info)
        #log(E_ERR, '%(ref)s [%(r_date)s --> %(d_date)s] %(delay)s' % info)
        return True

        qs = queries[mode] % info
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
            try:
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

                ## Parse/split all values
                data = {}
                parts = re_msg.split(msg)
                if len(parts) == 0: continue
                for part in parts:
                    part = part.strip()
                    if part.find('=') == -1: continue
                    key, value = part.split('=', 1)
                    data[key] = value

                info.update(data)
                if info.has_key('status'):
                    info['status'], info['status_desc'] = info['status'].split(' ', 1)

                ## TODO try/except
                res = handler(info.copy())
            except:
                t, val, tb = exc_info()
                self.log(E_ERR, 'Runtime Error: ' + str(val))
                pass

    ## Merge message_id and date and put them into the cache db
    def postfix_cleanup(self, info):
        if not info.has_key('message-id'):
            self.log(E_ERR, 'postfix/cleanup got no message_id ' + info['msg'])
            return False
        ### note message-id and not message_id
        self.addkey(info['ref'], '|'.join([info['ddatestr'], info['message-id']]))

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

        if not info.has_key('to'): return False

        if info.has_key('relay'):
            info['relay'] = info['relay'].split('[')[0]
        else:
            info['relay'] = 'none'

        if info['relay'] in self.skiplist: return True

        ## Parse mailto using rfc822 module
        try:
            info['mailto'] = parseaddr(info['to'])[1]
        except:
            log(E_ERR, 'Error while parsing mailto address, ' + info['to'])
            return False

        ## Parse delivery date
        ddatestr = info['ddatestr']
        try:
            info['d_date'] = DateTimeFromString(ddatestr)
        except:
            log(E_ERR, 'Error parsing sent date string, ' + ddatestr)
            return False

        ## Parse received date
        rdatestr, info['message_id'] = self.db[ref].split('|', 1)
        try:
            info['r_date'] = DateTimeFromString(rdatestr)
        except:
            log(E_ERR, 'Error parsing received date string, ' + rdatestr)
            return False

        return self.insert('mta', info)

    #postfix_lmtp = postfix_smtp
    def postfix_lmtp(self, info):
        return True

    def sendmail_sendmail(self, info):
        ref = info['ref']
        if info.has_key('from') and info.has_key('msgid'):
            if info['from'] == '<>': return True # no return path
            self.addkey(ref, '|'.join([info['ddatestr'], info['msgid']]))
        elif info.has_key('to'):
            if not self.db.has_key(ref): return False
            rdatestr, info['message_id'] = self.db[ref].split('|', 1)
            self.delkey(ref) # remove reference in cache

            if info.has_key('relay'):
                info['relay'] = info['relay'].split(' ', 1)[0]
            else:
                info['relay'] = 'none'

            if info['relay'] in self.skiplist: return True

            ## Parse mailto using rfc822 module
            try:
                info['mailto'] = parseaddr(info['to'])[1]
            except:
                log(E_ERR, 'Error while parsing mailto address, ' + info['to'])
                return False

            ## Parse delivery date
            ddatestr = info['ddatestr']
            try:
                info['d_date'] = DateTimeFromString(ddatestr)
            except:
                log(E_ERR, 'Error parsing sent date string, ' + ddatestr)
                return False

            ## Parse received date
            try:
                info['r_date'] = DateTimeFromString(rdatestr)
            except:
                log(E_ERR, 'Error parsing received date string, ' + rdatestr)
                return False

            info['status'], info['status_desc'] = info['stat'].split(' ', 1)
            info['status'] = info['status'].lower()
            return self.insert('mta', info)
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
