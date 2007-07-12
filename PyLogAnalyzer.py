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

from sys import exc_info, stdin
from types import StringType
from rfc822 import parseaddr
from mx.DateTime.Parser import DateTimeFromString
from psycopg2 import connect
import re

DBDSN = 'host=localhost dbname=mail user=archiver password=mail'

re_line = re.compile(r'(\w+\s+\d+\s+\d+:\d+:\d+) (.*?) (.*?)\[(\d*?)\]: (.*)')
re_msg  = re.compile(r'(\w+=.*?),')

re_pstat = re.compile(r'(\w+) \((.*)\)')

defskiplist = [ 'none', '127.0.0.1', 'localhost' ]

E_ALWAYS = 0
E_INFO   = 1
E_WARN   = 2
E_ERR    = 3
E_TRACE  = 4

loglevel = E_ERR

### Queries

q_postfix_msgid = """
insert into mail_log_in (
    message_id,
    r_date,
    ref
) values (
    '%(message_id)s',
    '%(date)s',
    '%(ref)s'
);"""

q_postfix_update = """
update mail_log_in set
    mailfrom  = '%(mailfrom)s',
    mail_size = %(mail_size)d,
    nrcpts    = %(nrcpts)d
where ref = '%(ref)s';
"""

q_sendmail_in = """
insert into mail_log_in (
    mailfrom,
    message_id,
    r_date,
    mail_size,
    nrcpts,
    ref
) values (
    '%(mailfrom)s',
    '%(message_id)s',
    '%(date)s',
    %(mail_size)d,
    %(nrcpts),
    '%(ref)s'
);
"""

q_out = """
insert into mail_log_out (
    mail_id,
    d_date,
    dsn,
    relay,
    delay,
    status,
    status_desc,
    mailto
) values (
    get_mail_id('%(ref)s'),
    '%(date)s',
    '%(dsn)s',
    '%(relay)s',
    %(delay)d,
    '%(status)s',
    '%(status_desc)s',
    '%(mailto)s'
);
"""

PyLog = None

def log(severity, text):
    if severity <= loglevel:
        print text

def sqlquote(text):
    return text.replace("'", "\\'")

def quotedict(info):
    for key in info.keys():
        if type(info[key]) == StringType:
            info[key] = sqlquote(info[key])

class PyLogAnalyzer:
    def __init__(self, filename, skiplist=defskiplist):
        self.log = log
        self.skiplist = skiplist

        try:
            self.dbConn = connect(DBDSN)
            self.dbCurr = self.dbConn.cursor()
        except:
            raise Exception, 'Cannot connect to DB'

        try:
            if filename == '-':
                self.fd = stdin
            else:
                self.fd = open(filename, 'r')
        except:
            raise Exception, 'Cannot open log file'

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

        self.log(E_ALWAYS, 'Job Done')

    def query(self, query, info):
        #log(E_ERR, str(info.keys()))
        #log(E_ERR, '%(ref)s [%(r_date)s --> %(d_date)s] %(delay)s' % info)
        #log(E_ERR, '%(ref)s: %(status)s - %(status_desc)s' % info)

        #return False
        quotedict(info)

        qs = query % info
        try:
            self.dbCurr.execute(qs)
            self.dbConn.commit()
        except:
            ## TODO Traceback
            log(E_ERR, 'DB Query Error')
            self.dbConn.rollback()

        return True

    def mainLoop(self):
        while 1:
            try:
                ## Read a line
                line = self.fd.readline().strip()

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

                ## split fields
                datestr, host, name, pid, line = res.groups()
                line = line.split(': ', 1)
                if len(line) != 2: continue
                ref, msg = line

                ## Parse date
                try:
                    date = DateTimeFromString(datestr).Format()
                except:
                    log(E_ERR, 'Error parsing date, ' + datestr)
                    continue

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
                info = dict(date=date,
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

                res = handler(info.copy())
            except (KeyboardInterrupt, IOError):
                break
            except:
                t, val, tb = exc_info()
                self.log(E_ERR, 'Runtime Error: ' + str(val))
                pass

    ## Merge message_id and date and put them into the cache db
    def postfix_cleanup(self, info):
        """ Collects message_id and inserts the record with the placeholder """
        if not info.has_key('message-id'):
            self.log(E_ERR, 'postfix/cleanup got no message_id ' + info['msg'])
            return False
        info['message_id'] = info['message-id']
        return self.query(q_postfix_msgid, info)

    ## qmgr log have from or queue deletions
    def postfix_qmgr(self, info):
        """ Collects from, size and nrcpt and updates record of postfix/cleanup """
        if not info.has_key('from'): return True # removed

        try:
            info['mail_size'] = long(info['size'])
        except:
            info['mail_size'] = 0

        try:
            info['nrcpts'] = long(info['nrcpt'].split(' ', 1)[0])
        except:
            info['nrcpts'] = 0

        ## Parse mailfrom using rfc822 module
        try:
            info['mailfrom'] = parseaddr(info['from'])[1]
        except:
            log(E_ERR, 'Error while parsing mailfrom address, ' + info['from'])
            return False

        return self.query(q_postfix_update, info)

    def postfix_smtp(self, info):
        """ Picks mail_id from the record of postfix/cleanup and fills mail_log_out entry """
        if not info.has_key('to'): return False # no need

        ## Skip 'connect to' - FIXME find a better way
        if len(info['ref']) != 11: return False

        if info.has_key('relay'):
            info['relay'] = info['relay'].split('[')[0]
        else:
            info['relay'] = 'none'

        if info['relay'] in self.skiplist: return True

        try:
            info['delay'] = long(info['delay'])
        except:
            info['delay'] = 0

        ## Parse mailto using rfc822 module
        try:
            info['mailto'] = parseaddr(info['to'])[1]
        except:
            log(E_ERR, 'Error while parsing mailto address, ' + info['to'])
            return False

        ## Parse status
        res = re_pstat.match(info['status'])
        if res:
            info['status'], info['status_desc'] = res.groups()
        else:
            info['status'], info['status_desc'] = 'unknown', info['status']

        return self.query(q_out, info)

    def sendmail_sendmail(self, info):
        """ Collects two stages of sendmail log """
        if info.has_key('from') and info.has_key('msgid'):
            ## Collects from, message_id and nrctps
            if info['from'] == '<>': return True # no return path
            ## Parse mailfrom using rfc822 module
            try:
                info['mailfrom'] = parseaddr(info['from'])[1]
            except:
                log(E_ERR, 'Error while parsing mailfrom address, ' + info['from'])
                return False

            try:
                info['nrcpts'] = long(info['nrcpts'])
            except:
                info['nrcpts'] = 0

            return self.query(q_sendmail_in, info)
        elif info.has_key('to'):
            ## Collects to, delay, relay, dns, status and status_desc
            ## Sendmail messages are not easy to parse
            status = info['stat']
            if status.startswith('Sent '):
                status, statusdesc = 'sent', status.split('Sent ', 1).pop()
            elif status.startswith('Deferred: '):
                status, statusdesc = 'deferred', status.split('Deferred: ', 1).pop()
            else:
                status, statusdesc = 'unknown', status

            info['status'] = status
            ## remove ( and )
            if (statusdesc[0] == '(') and (statusdesc[-1] == ')'):
                statusdesc = statusdesc[1:-1]
            info['status_desc'] = statusdesc

            if info.has_key('relay'):
                info['relay'] = info['relay'].split(' ', 1)[0]
            else:
                info['relay'] = 'none'

            ## Conformance with postfix
            if info['relay'][-1] == '.': info['relay'] = info['relay'][:-1]
            if info['relay'] in self.skiplist: return True

            ## Parse mailto using rfc822 module
            try:
                info['mailto'] = parseaddr(info['to'])[1]
            except:
                log(E_ERR, 'Error while parsing mailto address, ' + info['to'])
                return False

            ## Parse delay
            try:
                hms = info['delay'].split(':')
                seconds = int(hms[2])
                seconds = seconds + (int(hms[1]) * 60)
                if hms[0].find('+') == -1:
                    d = 0
                    h = int(hms[0])
                else:
                    d, h = hms[0].split('+')
                    d = int(d)
                    h = int(h)
                seconds = seconds + (h * 60 * 60)
                seconds = seconds + (d * 24 * 60 * 60)
                info['delay'] = long(seconds)
            except:
                info['delay'] = 0

            return self.query(q_out, info)
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
