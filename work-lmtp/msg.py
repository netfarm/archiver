#!/usr/bin/env python
from mimetools import Message
m = Message(open("116.eml"))

#for h in m.dict.keys():
#	print "%s: %s" % (h, m.dict[h].replace('\r','\\r').replace('\n','\\n'))

#print "*"*78
#print m.headers


headers = {}

for h in m.headers:
	h = h.strip()
	if h.find(':')==-1: continue
	key, value = h.split(':', 1)
	if headers.has_key(key):
		print "Duplicate:", key, value
		continue
	headers[key] = value

for h in headers.keys():
	print "%s: %s" % (h, headers[h])
