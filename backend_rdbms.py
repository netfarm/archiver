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
## @file backend_rdbms.py
## RDBMS Storage and Archive Backend

__doc__ = '''Netfarm Archiver - release 2.0.0 - Rdbms backend'''
__version__ = '2.0.0'
__all__ = [ 'Backend' ]

## TODO Win32 use different driver??
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

##
def sql_quote(v):
    """sql_quote

    quotes special chars and removes NULL chars
    @param v: is the text that should be quoted
    @return: quoted string"""
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
    """Formats an error message from rdbms backend

    removes tabs and replaces cr with commas, also trims the msg to 256 chars
    @param msg: is the original object for error message
    @return: formatted message"""
    msg = str(msg)
    if len(msg)>256:
        msg = msg[:256] + '...(message too long)'
    msg = ', '.join(msg.strip().split('\n'))
    msg = msg.replace('\t', '')
    return msg

class BadConnectionString(Exception):
    """BadConnectionString The specified connection string is wrong"""
    pass

class ConnectionError(Exception):
    """ConnectionError An error occurred when connecting to RDBMS"""
    pass

class Backend(BackendBase):
    """RDBMS Backend outputs to a relational database

        This backend only supports postgresql for now, it can be used either as
        Storage either as Archive"""
    def __init__(self, config, stage_type, ar_globals):
        """The constructor

        Initialize a connection to a rdbms"""
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
        """make a connection to rdbms

        raises ConnectionError if fails"""
        self.close()
        try:
            self.connection = self.db_connect(self.dsn)
        except:
            ## We can work without the db connection and call it when needed
            t, val, tb = exc_info()
            del tb
            msg = format_msg(val)
            self.LOG(E_ERR, 'Rdbms Backend: connection to database failed: ' + msg)
            raise ConnectionError, msg
            
        try:
            self.connection.autocommit(1)
            #self.connection.set_isolation_level(0)
        except:
            self.LOG(E_TRACE, 'Rdbms Backend: driver has not isolation_level facility')
        self.cursor = self.connection.cursor()
        self.LOG(E_TRACE, 'Rdbms Backend: I\'ve got a cursor from the driver')


    def do_query(self, qs, fetch=None):
        """execute a query

        Query -> reconnection -> Query
        @param qs: the query string
        @param fetch: is defined then the query must return a result
        @return: year, pid, message, if year is 0 an error is occured,
                 pid has the code, message contains a more detailed explanation"""
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
        """process data from archiver main process

        Creates a query by using data passed by the main archiver process
        @param data: is a dict containing all needed stuff
        @return: the result of do_query"""
        
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
        """process storaging of mail on a rdbms

        The query doesn't return rows but only result code
        @param data: is a dict containg year, pid and mail from archiver
        @return: result code"""
        msg = { 'year': data['year'],
                'pid' : data['pid'],
                'mail': encodestring(data['mail'])
                }
        
        return self.do_query(self.query[0] % msg)
        
    def shutdown(self):
        """shutdown the rdbms stage

        closes the rdbms connection and the stage Thread"""
        self.close()
        self.LOG(E_ALWAYS, 'Rdbms Backend (%s): closing connection' % self.type)
