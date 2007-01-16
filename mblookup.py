#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2
#
# Copyright (C) 2005-2007 Gianluigi Tiesi <sherpya@netfarm.it>
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
## @file compress.py
## Helper for file compression

__doc__ = '''Netfarm Archiver - release 2.0.0 - Postfix mailbox lookup'''
__version__ = '2.0.0'
__all__ = [ 'mblookup' ]

from anydbm import open as opendb
import sys

aliases = '/etc/postfix/aliases.db'
virtual = '/etc/postfix/virtual.db'

def lookup_alias(dba, bc, alias):
    al = dba.get(alias, None)
    if al is None:
        return [alias[:-1].strip()]

    alist = al[:-1].strip().split(',')
    if len(alist) == 1: return [al[:-1].strip()]
    res = []
    for al in alist:
        al = al.strip()
        if al in bc: return [] # Loop
        bc.append(al)
        al = al + '\x00'
        res = res + lookup_alias(dba, bc, al)
    return res

def lookup(dba, dbv, email):
    email = email + '\x00'
    mbox = dbv.get(email, None)

    if mbox is None: # No match
        return []
    if mbox.find('@') != -1: # External
        return []

    bc = []
    return lookup_alias(dba, bc, mbox)

# Postfix db files
def mblookup(emails):
    dba = opendb(aliases, 'r')
    dbv = opendb(virtual, 'r')

    results = []

    for email in emails:
        results = results + lookup(dba, dbv, email)

    dba.close()
    dbv.close()
    return results
