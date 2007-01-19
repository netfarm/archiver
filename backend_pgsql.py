#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2
#
# Copyright (C) 2005-2007 Gianluigi Tiesi <sherpya@netfarm.it>
# Copyright (C) 2005-2007 NetFarm S.r.l.  [http://www.netfarm.it]
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
## @file backend_pgsql.py
## PostgreSQL Storage and Archive Backend

__doc__ = '''Netfarm Archiver - release 2.1.0 - PostgreSQL backend'''
__version__ = '2.1.0'
__all__ = [ 'Backend' ]

from archiver import *
from sys import exc_info
from time import asctime
from base64 import encodestring
from psycopg2 import connect as db_connect
from mblookup import mblookup

mail_template = """
INSERT INTO mail (
    mail_id,
    year,
    pid,
    message_id,
    from_login,
    from_domain,
    subject,
    mail_date,
    attachment,
    media
) VALUES (
    get_next_mail_id(),
    get_curr_year(),
    get_new_pid(),
    '%(message_id)s',
    '%(from_login)s',
    '%(from_domain)s',
    '%(subject)s',
    '%(date)s',
    %(attachment)s,
    -1
);
"""

recipient_template = """
INSERT INTO recipient (
    mail_id,
    to_login,
    to_domain
) VALUES (
    get_curr_mail_id(),
    '%(to_login)s',
    '%(to_domain)s'
);
"""
authorized_template = """
INSERT INTO authorized (
    mail_id,
    mailbox
) VALUES (
    get_curr_mail_id(),
    '%s'
);
"""

storage_template = """
INSERT INTO mail_storage (
    year,
    pid,
    mail
) VALUES (
    '%(year)d',
    '%(pid)d',
    '%(mail)s'
);
"""

##
def sql_quote(v):
    """sql_quote

    quotes special chars and removes NULL chars
    @param v: is the text that should be quoted
    @return: quoted string"""
    quote_list = [ '\'', '"', '\\' ]
    res = ''
    # Remove NULL - very bad emails
    v = v.replace('\x00', '')
    for i in range(len(v)):
        if v[i] in quote_list:
            res = res + '\\'
        res = res + v[i]
    return res

def format_msg(msg):
    """Formats an error message from pgsql backend

    removes tabs and replaces cr with commas, also trims the msg to 256 chars
    @param msg: is the original object for error message
    @return: formatted message"""
    msg = str(msg)
    if len(msg) > 256:
        msg = msg[:256] + '...(message too long)'
    msg = ', '.join(msg.strip().split('\n'))
    msg = msg.replace('\t', '')
    return msg

class BadConnectionString(Exception):
    """BadConnectionString The specified connection string is wrong"""
    pass

class ConnectionError(Exception):
    """ConnectionError An error occurred when connecting to PGSQL"""
    pass

class Backend(BackendBase):
    """PGSQL Backend uses PostgreSQL database

        This backend can be used either as Storage either as Archive"""
    def __init__(self, config, stage_type, ar_globals, prefix = None):
        """The constructor

        Initialize a connection to pgsql"""
        if prefix is None:
            self._prefix = 'PGSQL Backend: '
        else:
            self._prefix = prefix
        self.config = config
        self.type = stage_type
        self.LOG = ar_globals['LOG']
        self.process = getattr(self, 'process_' + self.type, None)
        if self.process is None:
            raise StorageTypeNotSupported, self.type

        try:
            dsn = self.config.get(self.type, 'dsn')
        except:
            dsn = 'Missing connection string'

        if dsn.count(':') != 3:
            raise BadConnectionString, dsn

        username, password, host, dbname = dsn.split(':')
        self.dsn = 'host=%s user=%s password=%s dbname=%s' % (host,
                                                              username,
                                                              password,
                                                              dbname)
        self.connection = None
        self.cursor = None
        try:
            self.connect()
        except: pass
        if prefix is None:
            self.LOG(E_ALWAYS, self._prefix + '(%s) at %s' % (self.type, host))

    def close(self):
        """closes the cursor and the connection"""
        try:
            self.cursor.close()
            del self.cursor
        except: pass

        try:
            self.connection.close()
            del self.connection
        except: pass

    def connect(self):
        """make a connection to pgsql

        raises ConnectionError if fails"""
        self.close()
        error = None
        try:
            self.connection = db_connect(self.dsn)
        except:
            ## We can work without the db connection and call it when needed
            t, val, tb = exc_info()
            del t, tb
            error = format_msg(val)

        if error is not None:
            self.LOG(E_ERR, self._prefix + 'connection to database failed: ' + error)
            raise ConnectionError, error

        self.connection.set_isolation_level(0)
        self.cursor = self.connection.cursor()
        self.LOG(E_TRACE, self._prefix + 'I\'ve got a cursor from the driver')

    def do_query(self, qs, fetch=False, autorecon=False):
        """execute a query

        Query -> reconnection -> Query
        @param qs: the query string
        @param fetch: if True the query must return a result
        @param autorecon: if a query fails a db reconnection is done
        @return: year, pid, message, if year is 0 an error is occured,
                 pid has the code, message contains a more detailed explanation"""
        try:
            self.cursor.execute(qs)
            self.connection.commit()
            if fetch:
                res = self.cursor.fetchone()
                return res[1], res[0], 'Ok'
            else:
                return BACKEND_OK
        except:
            try:
                self.connection.rollback()
            except:
                self.LOG(E_ERR, self._prefix + 'rollback failed')
            self.LOG(E_ERR, self._prefix + 'query fails')
            if autorecon:
                self.LOG(E_ERR, self._prefix + 'Trying to reopen DB Connection')
                error = None
                try:
                    self.connect()
                except:
                    error = 'Error reopening DB connectin'
                if error is not None:
                    return 0, 443, 'Internal Server Error - ' + error
                return self.do_query(qs, fetch)
            else:
                t, val, tb = exc_info()
                del tb
                msg = format_msg(val)
                self.LOG(E_ERR, self._prefix + 'Cannot execute query: ' + msg)
                self.LOG(E_ERR, self._prefix + 'the query was: ' + qs)
                return 0, 443, '%s: Internal Server Error' % t

    def parse_recipients(self, recipients):
        result = []
        for recipient in recipients:
            try:
                dlog, ddom = recipient[1].split('@', 1)
            except:
                self.LOG(E_ERR, self._prefix + 'Error parsing to/cc: ' + recipient[1])
                dlog = recipient[1]
                ddom = recipient[1]

            result.append({'to_login': dlog, 'to_domain': ddom })
        return result

    def process_archive(self, data):
        """process data from archiver main process

        Creates a query by using data passed by the main archiver process
        @param data: is a dict containing all needed stuff
        @return: the result of do_query"""

        ## Safety check
        if (len(data['m_from']) == 0) or ((len(data['m_to']) + len(data['m_cc'])) == 0):
            return 0, 443, 'Integrity error missing From/To/Cc'

        # Conversions
        nattach = len(data['m_attach'])
        subject = sql_quote(mime_decode_header(data['m_sub'])[:252])
        date = sql_quote(asctime(data['m_date']))

        try:
            slog, sdom = data['m_from'][1].split('@')
            slog = slog.strip()
            sdom = sdom.strip()
        except:
            return 0, 443, 'Error splitting From address'

        values = { 'message_id': sql_quote(data['m_mid'][:508]),
                   'from_login': sql_quote(slog[:28]),
                   'from_domain': sql_quote(sdom[:255]),
                   'subject': sql_quote(subject[:252]),
                   'date': date,
                   'attachment': nattach }

        addrs = data['m_to'] + data['m_cc']
        recipients = self.parse_recipients(addrs)
        mbcheck = []
        mbcheck.append(data['m_from'][1])
        for addr in addrs:
            mbcheck.append(addr[1])
        mboxes = mblookup(mbcheck)

        qs = mail_template % values

        for recipient in recipients:
            qs = qs + recipient_template % recipient

        for mailbox in mboxes:
            qs = qs + authorized_template % mailbox

        qs = qs + 'SELECT pid, year from mail_pid;'

        year, pid, result = self.do_query(qs, True, True)
        return year, pid, result

    def process_storage(self, data):
        """process storaging of mail on pgsql

        The query doesn't return rows but only result code
        @param data: is a dict containg year, pid and mail from archiver
        @return: result code"""
        msg = { 'year': data['year'],
                'pid' : data['pid'],
                'mail': encodestring(data['mail'])
                }

        return self.do_query(storage_template % msg)

    def shutdown(self):
        """shutdown the PGSQL stage

        closes the pgsql connection and the stage Thread"""
        self.close()
        self.LOG(E_ALWAYS, self._prefix + '(%s): closing connection' % self.type)
