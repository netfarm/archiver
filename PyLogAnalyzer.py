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

## TODO
## - handle db disconnection
## - close fd when damonize

from sys import stdin, stdout
from os import chdir, fork
from traceback import format_exc
from types import StringType
from rfc822 import parseaddr
from mx.DateTime.Parser import DateTimeFromString
from psycopg2 import connect
import re

DBDSN = 'host=localhost dbname=mail user=archiver password=archiver'

re_line = re.compile(r'(\w+\s+\d+\s+\d+:\d+:\d+) (.*?) (.*?)\[(\d*?)\]: (.*)')
re_msg  = re.compile(r'(\w+=.*?), ')

re_pstat = re.compile(r'(\w+) \((.*)\)')

defskiplist = [ '127.0.0.1', 'localhost' ]

E_ALWAYS = 0
E_INFO   = 1
E_WARN   = 2
E_ERR    = 3
E_TRACE  = 4

global logfd

loglevel = E_TRACE
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
where id in (select id
             from mail_log_in
             where ref = '%(ref)s'
             order by r_date desc
             limit 1);
"""

q_postfix_del = """
delete from mail_log_in
where id
in (select id from mail_log_in where ref = '%(ref)s'
    order by id desc limit 1);
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
    %(nrcpts)d,
    '%(ref)s'
);
"""

q_mail_id = """
select id from mail_log_in
where ref = '%(ref)s'
order by r_date desc
limit 1;
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
    %(mail_id)d,
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
        logfd.write(text + '\n')
        logfd.flush()

def sqlquote(text):
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    return text

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
            self.dbCursor = self.dbConn.cursor()
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
            self.dbCursor.close()
            self.dbConn.close()
        except:
            pass

        try:
            self.fd.close()
        except:
            pass

        self.log(E_TRACE, 'Exit')

    def query(self, query, info, fetch=False):
        quotedict(info)
        qs = query % info

        try:
            self.dbCursor.execute(qs)
            self.dbConn.commit()
        except KeyboardInterrupt:
            raise KeyboardInterrupt
        except:
            log(E_ERR, '-----------\n[DB Query Error]')
            log(E_ERR, format_exc().strip())
            log(E_ERR, '\n[Query]\n' + qs)
            log(E_ERR, '-----------')
            try:
                self.dbConn.rollback()
            except:
                pass
            return False

        if fetch:
            return self.dbCursor.fetchone()
        else:
            return True

    def mainLoop(self):
        self.log(E_ALWAYS, '[PyLogAnalyzer] Starting...')
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
                hname = '_'.join([process, subprocess]).replace('-', '_')
                handler = getattr(self, hname, None)
                if handler is None: continue

                ## Map fields
                info = dict(date=date,
                            host=host,
                            pid=pid,
                            ref=ref,
                            msg=msg,
                            process=process,
                            subprocess=subprocess)

                ## Parse/split all values
                data = { 'dsn': '0.0.0' } # postfix and some lines on sendmail
                parts = re_msg.split(msg)
                if len(parts) == 0: continue
                for part in parts:
                    part = part.strip()
                    if part.find('=') == -1: continue
                    key, value = part.split('=', 1)
                    data[key] = value

                info.update(data)

                if not handler(info.copy()):
                    log(E_ERR, 'Query Failed - Force Respawn (syslog-ng)')
                    break
            except (KeyboardInterrupt, IOError):
                break
            except:
                log(E_ERR, '-----------\n[Runtime Error]')
                log(E_ERR, format_exc().strip())
                log(E_ERR, '-----------')

    ## Gather message_id and put the entry in the database
    def postfix_cleanup(self, info):
        """ Collects message_id and inserts the record with the placeholder """
        if info['msg'].startswith('reject:'): return True
        if info.has_key('resent-message-id'): return True
        if not info.has_key('message-id'):
            self.log(E_ERR, 'postfix/cleanup got no message_id %s: %s' % (info['ref'],  info['msg']))
            return True
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
            return True

        return self.query(q_postfix_update, info)

    def postfix_smtp(self, info):
        """ Picks mail_id from the record of postfix/cleanup and fills mail_log_out entry """
        if not info.has_key('to'): return True # no need

        ## Skip 'connect to' - FIXME find a better way postfix in etch 11, sarge 9, lenny 10 ??
        if len(info['ref']) not in (9, 10, 11): return True

        ## Retrieve ref's mail_id
        mail_id = self.query(q_mail_id, info, fetch=True)
        if mail_id is None: return True
        info['mail_id'] = mail_id[0]

        if info.has_key('relay'):
            info['relay'] = info['relay'].split('[')[0]
        else:
            info['relay'] = 'none'

        if info['relay'] in self.skiplist:
            return self.query(q_postfix_del, info)

        try:
            info['delay'] = long(info['delay'])
        except:
            info['delay'] = 0

        ## Parse mailto using rfc822 module
        try:
            info['mailto'] = parseaddr(info['to'])[1] # FIXME multiple recipients as in sendmail?
        except:
            log(E_ERR, 'Error while parsing mailto address, ' + info['to'])
            return True

        ## Parse status
        res = re_pstat.match(info['status'])
        if res:
            info['status'], info['status_desc'] = res.groups()
        else:
            info['status'], info['status_desc'] = 'unknown', info['status']

        return self.query(q_out, info)

    postfix_lmtp = postfix_smtp

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
                return True

            try:
                info['mail_size'] = long(info['size'])
            except:
                info['mail_size'] = 0

            try:
                info['nrcpts'] = long(info['nrcpts'])
            except:
                info['nrcpts'] = 0

            ## Now message_id as required dict key
            info['message_id'] = info['msgid']

            return self.query(q_sendmail_in, info)
        elif info.has_key('to'):
            ## Collects to, delay, relay, dns, status and status_desc

            ## First check if we have a corresponding mail_id
            mail_id = self.query(q_mail_id, info, fetch=True)
            if mail_id is None: return True
            info['mail_id'] = mail_id[0]

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

            recipients = info['to'].split(',')

            info['recipients'] = []
            for recipient in recipients:
                try:
                    info['recipients'].append(parseaddr(recipient)[1])
                except:
                    log(E_ERR, 'Error while parsing mailto address, ' + info['to'])

            if len(info['recipients']) == 0:
                log(E_ERR, 'No recipients collected - skipping')
                return True

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

            res = True
            for recipient in info['recipients']:
                info['mailto'] = recipient
                res = res and self.query(q_out, info)
            return res
        else:
            return True # ignored

    sm_mta_sm_mta = sendmail_sendmail

def sigtermHandler(signum, frame):
    log(E_ALWAYS, 'SiGTERM received')

if __name__ == '__main__':
    global logfd
    from sys import argv, exit as sys_exit
    from signal import signal, SIGTERM

    if '-l' in argv:
        skiplist = []
        argv.remove('-l')
    else:
        skiplist = defskiplist

    if '-d' in argv:
        daemonize = True
        logfd = open('/var/log/pylog.log', 'a')
        argv.remove('-d')
    else:
        logfd = stdout
        daemonize = False

    if '-ng' in argv:
        logfd = open('/var/log/pylog.log', 'a')
        argv.remove('-ng')

    if len(argv) != 2:
        print 'Usage %s [-d] [-ng] [-l] logfile|fifo' % argv[0]
        sys_exit()

    if daemonize and (argv[0] == '-'):
        print '%s incompatible options -d with stdin'
        sys_exit()

    signal(SIGTERM, sigtermHandler)
    if daemonize:
        pid = fork()
        if pid: sys_exit(0)
        chdir('/')

    try:
        PyLog = PyLogAnalyzer(argv[1], skiplist)
        PyLog.mainLoop()
    except:
        log(E_ERR, '-----------\n[Startup Error]')
        log(E_ERR, format_exc().strip())
        log(E_ERR, '-----------')
