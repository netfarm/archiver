#!/usr/bin/env python

from sys import argv
from lmtp import getaddr

email = argv[1]
if email[0]!='<':
	email = '<'+email+'>'

e = 'FROM: ' + email

res = getaddr('FROM:', e)

print "Checking: %s - results: [%s] [%s]" % (email, res[0], res[1])
 
