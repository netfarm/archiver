#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2.x
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
## @file backend_rdbms.py
## @brief RDBMS Storage and Archive Backend

__doc__ = '''Netfarm Archiver - release 2.x - Rdbms backend'''
__version__ = '2.0a1'
__all__ = [ 'Backend' ]

driver_map = { 'psql': 'psycopg' }

qs_map = { 'archive':
		   ['''INSERT INTO mail
		   (year,
		   pid,
		   from_login,
		   from_domain,
		   to_login,
		   to_domain,
		   subject,
		   mail_date,
		   attachment)
		   VALUES
		   (int4(EXTRACT (YEAR FROM NOW())),
		   (SELECT max(pid) + 1 FROM mail_pid),
		   '%(from_login)s',
		   '%(from_domain)s',
		   '%(to_login)s',
		   '%(to_domain)s',
		   '%(subject)s',
		   '%(date)s',
		   '%(attachments)d');
		   ''',
			'''UPDATE mail_pid
			SET pid  = (pid+1) * (1 - (int2(EXTRACT (YEAR FROM NOW())) - year)),
			year = int2(EXTRACT (YEAR FROM NOW()));
			SELECT max(pid) as pid,
			max(year) as pid_year
			FROM mail_pid;'''],

		   
		   'storage':
		   ['''INSERT INTO mail_storage
           (year,
           pid,
           mail)
           VALUES
           ('%(year)d',
           '%(pid)d',
           '%(mail)s');''', '']
		   }

from archiver import *
from sys import exc_info
from time import asctime
from base64 import encodestring

def sql_quote(v):
    quote_list = [ '\'', '"', '\\' ]
    res = ''
    # Remove NULL - very bad mails
    v = v.replace('\x00', '')
    for i in range(len(v)):
        if v[i] in quote_list:
            res = res + '\\'
        res = res + v[i]
    return res

def format_msg(msg):
    msg = str(msg)
    if len(msg)>256:
        msg = msg[:256] + '...(message too long)'
    msg = ', '.join(msg.strip().split('\n'))
    msg = msg.replace('\t', '')
    return msg

class BadConnectionString(Exception):
    """@exception BadConnectionString The specified connection string is wrong
    @brief Exception: The specified connection string is wrong"""
    pass

class ConnectionError(Exception):
    """@exception ConnectionError An error occurred when connecting to RDBMS
    @brief Exception: An error occurred when connecting to RDBMS"""
    pass

class Backend(BackendBase):
    """@brief RDBMS Backend outputs to a relational database

        This backend only supports postgresql for now, it can be used either as
        Storage either as Archive"""
    def __init__(self, config, stage_type, ar_globals):
        self.config = config
        self.type = stage_type
        self.query = qs_map.get(self.type, None)
        if self.query is None:
            raise StorageTypeNotSupported, self.type 
        self.LOG = ar_globals['LOG']
		self.process = getattr(self, 'process_' + self.type, None)
		if self.process is None:
            raise StorageTypeNotSupported, self.type

        try:
            dsn = config.get(self.type, 'dsn', None)
            driver, username, password, host, dbname = dsn.split(':')
            self.driver = driver_map[driver]
            self.dsn = "host=%s user=%s password=%s dbname=%s" % (host,
                                                                  username,
                                                                  password,
                                                                  dbname)
        except:
            raise BadConnectionString

        try:
            self.db_connect = getattr(__import__(self.driver, globals(), locals(), []), 'connect', None)
        except ImportError:
            raise Exception, 'Rdbms Backend: Driver not found'

        if self.db_connect is None:
            raise Exception, 'Rdbms Backend: Driver misses connect method'
        
        self.connection = None
        self.cursor = None
        try:
            self.connect()
        except: pass
        self.LOG(E_ALWAYS, 'Rdbms Backend (%s) %s at %s' % (self.type, driver, host))
        del ar_globals

   
    def close(self):
        if self.cursor:
            try:
                self.cursor.close()
            except: pass
            self.cursor = None
        if self.connection:
            try:
                self.connection.close()
            except: pass
            self.connection = None

    def connect(self):
        self.close()
        try:
            self.connection = self.db_connect(self.dsn)
        except:
            ### We can work without the db connection and call it when needed
            t, val, tb = exc_info()
            del tb
            msg = format_msg(val)
            self.LOG(E_ERR, 'Rdbms Backend: connection to database failed: ' + msg)
            raise ConnectionError, msg
            
        try:
            self.connection.autocommit(1)
        except:
            self.LOG(E_TRACE, 'Rdbms Backend: driver has not autocommit facility')
        self.cursor = self.connection.cursor()
        self.LOG(E_TRACE, 'Rdbms Backend: I\'ve got a cursor from the driver')


    def do_query(self, qs, fetch=None):
        ### Query -> reconnection -> Query
        try:
            self.cursor.execute(qs)
            if fetch:
                res = self.cursor.fetchone()
                return res[1], res[0], 'Ok'
            else:
                return BACKEND_OK
        except:
            self.LOG(E_ERR, 'Rdbms Backend: query fails, maybe disconnected')
            try:
                self.connect()
                self.cursor.execute(qs)
                if fetch:
                    res = self.cursor.fetchone()
                    return res[1], res[0], 'Ok'
                else:
                    return BACKEND_OK
            except:
                t, val, tb = exc_info()
                del tb
                msg = format_msg(val)
                self.LOG(E_ERR, 'Rdbms Backend: Cannot execute query: ' + msg)
                self.LOG(E_ERR, 'Rdbms Backend: failed query was: ' + qs)
                return 0, 443, '%s: Internal Server Error' % t

    def process_archive(self, data):
        qs = ''
        nattach = len(data['m_attach'])
        subject = sql_quote(mime_decode_header(data['m_sub'])[:252])
        date = sql_quote(asctime(data['m_date']))
        for sender in data['m_from']:
            try:
                slog, sdom = sender[1].split('@', 1)
            except:
                self.LOG(E_ERR, 'Error parsing from: ' + sender[1])
                slog = sender[1]
                sdom = sender[1]
            
            for dest in data['m_to']+data['m_cc']:
                try:
                    dlog, ddom = dest[1].split('@',1)
                except:
                    self.LOG(E_ERR, 'Error parsing to/cc: ' + dest[1])
                    dlog = dest[1]
                    ddom = dest[1]
            
                values = { 'from_login': sql_quote(slog[:28]),
                           'from_domain': sql_quote(sdom[:255]),
                           'to_login': sql_quote(dlog[:28]),
                           'to_domain': sql_quote(ddom[:255]),
                           'subject': subject,
                           'date': date,
                           'attachments': nattach }
                qs = qs + (self.query[0] % values)

        qs = qs + self.query[1]

        return self.do_query(qs, fetch=1)
    
    def process_storage(self, data):
        msg = { 'year': data['year'],
                'pid' : data['pid'],
                'mail': encodestring(data['mail'])
                }
        
        return self.do_query(self.query[0] % msg)
        
    def shutdown(self):
        self.close()
        self.LOG(E_ALWAYS, 'Rdbms Backend (%s): closing connection' % self.type)
