#!/usr/bin/env python
from mimetools import Message
from sys import argv
from time import *
from rfc822 import parsedate
m = Message(open(argv[1]))


#m_date = mktime(m.getdate('Date'))
#s_date = mktime(localtime(time()))

m_date = m.getdate('Date')
s_date = localtime(time())

print m_date
print asctime(m_date)
print "--"
print s_date
print asctime(s_date)
