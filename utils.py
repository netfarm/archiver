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
## @file utils.py
## Common utils

import re
from mimify import mime_decode
from base64 import decodestring
from rfc822 import parseaddr
from md5 import new as MD5

mime_head = re.compile('=\\?(.*?)\\?(\w)\\?([^? \t\n]+)\\?=', re.IGNORECASE)
encodings = { 'q': mime_decode, 'b': decodestring }

CHECKHEADERS = [ 'from', 'subject', 'date', 'message-id', 'x-archiver-id' ]
HASHHEADERS  = [ 'message-id', 'from', 'to', 'cc', 'subject' ]

def mime_decode_header(line):
    """workaround to python mime_decode_header

    The original code doesn't support base64"""
    ## TODO: check combined charsets headers
    newline = ''
    charset = 'latin-1'
    pos = 0
    while 1:
        res = mime_head.search(line, pos)
        if res is None:
            break
        charset = res.group(1)
        enctype = res.group(2).lower()
        match = res.group(3)
        if encodings.has_key(enctype):
            match = ' '.join(match.split('_'))
            newline = newline + line[pos:res.start(0)] + encodings[enctype](match)
        else:
            newline = newline + line[pos:res.start(0)] + match
        pos = res.end(0)

    decoded = newline + line[pos:]
    return decoded.decode(charset, 'replace')

def unquote(text):
    return ''.join(text.split('"'))

def split_hdr(header, value, dict):
    """ Multiline headers splitting"""
    hdr = '='.join([header, value]).replace('\r', '').replace('\n', '')
    hdr_list = hdr.split(';')
    for hdr in hdr_list:
        hdr = hdr.strip()
        if hdr.find('=') == -1: continue # invalid
        key, value = hdr.split('=', 1)
        if len(value) == 0: continue # empty
        key = key.strip()
        value = unquote(value).strip()
        dict[key] = value

def parse_message(submsg):
    """Parse a sub message"""
    found = None
    if submsg.dict.has_key('content-type'):
        ct = submsg.dict['content-type']
        hd = {}
        split_hdr('Content-Type', ct, hd)

        if submsg.dict.has_key('content-disposition'):
            cd = submsg.dict['content-disposition']
            split_hdr('Content-Disposition', cd, hd)

        ### Hmm nice job clients, filename or name?
        if not hd.has_key('name') and hd.has_key('filename'):
            hd['name'] = hd['filename']

        ### Found an attachment
        if hd.has_key('name'):
            found = { 'name': hd['name'], 'content-type': hd['Content-Type'] }
    return found

def dupe_check(headers):
    """Check for duplicate headers

    Some headers should be unique"""
    check = []
    for hdr in headers:
        hdr = hdr.strip()
        if hdr.find(':') == -1: continue
        key = hdr.split(':', 1)[0]
        key = key.lower()
        if key in check and key in CHECKHEADERS:
            return key
        check.append(key)
    return None

def safe_parseaddr(address):
    address = parseaddr(address)[1]
    if address is None or (address.find('@') == -1):
        return None
    l, d = address.split('@', 1)
    l = l.strip()
    d = d.strip()
    if (len(l) == 0) or (len(d) == 0):
        return None
    return address

def hash_headers(getter):
    m = MD5()
    for header in HASHHEADERS:
        m.update(getter(header, ''))
    return m.hexdigest()
