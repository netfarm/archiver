Version History

* Version 0.1 - may 3 2002
   base parsing of mails, it extracts the needed fields and the number of attachments

* Version 0.2 - may 4 2002
   mime_decode_header translates suject from quoted printable to 8 bit
   peraps mail made by LookOut are utf-8 and iso-8859-1 are not decoded
   XML-RPM module to talk with zope is ready... I've made a class for
   xmlrpclib to permit basic authrization. It is taken from a patch of
   Amos, a zope developer, but I've preferred to pass directly auth string base64encoded
   for performance reasons

* Version 0.3 - may 5 2002
   added xmlrpc module for talking with zope, zope must return a tuple (year,pid)

* Version 0.4 - may 7 2002
   date parsing, mimify modules is bad and need a rewrite, I'm looking at rfc

* Version 0.5 - may 13 2002
   added mimify_ext module to fix standard python mimify

* Version 0.6 - may 24 2002
   added rerouting mail part, misses error handling

* Version 0.7 - may 26 2002
   modifing subject is working, also if mail has no subject header, if mail has more than one
   subject header, only the first is changed... but how hell is sending mails with more than
   one subject?

* Version 0.8 - jun 4 2002
   Reworked logging system, now is more functional, there is a loglevel concept
   the syntax is LOG(loglevel, msg) where is E_NONE,E_ERR,E_INFO,E_TRACE

* Version 0.9 - jun 29 2002
   mimify_ext modules is now withing zope Extensions 
   coded error handling flow (what it should do if this reported problem... etc)
   sending mail function now has error handling
   it sends a mail to sender if it cannot deliver the mail and destination domain is handled
   by the smtp server (amavis has this bug)
   authstring is not base64encoded but username:password
   Made a "main", this is usefull for testing single function and I'm approcing to convert
   the filter into a daemon
   completed xmlprc save e failsafe
   completed report_adminbackup

* Version 1.0rc1 - jul 15 2002
   now is a multithreaded daemon and listen on unix socket
   sigint is handled correctly, the main thread waits for thread childs termination
   python should do this anyway but is not so clean
   reloading of configuration seams a bit complicated
   I should import config and use settings with config.variable
   added makemail function for mail formatting with headers
   fixed some typos
   store function now logs errors
   made locking function and check for the process if it's still alive

* Version 1.0rc2 - jul 30 2002
  - error handling Test
  - fixed a bug in storage on filesystem
  - stress test even with inject.c, peraps I miss some base tests on inject.c

* Version 1.0 - aug 27 2003
  - fixed handling of non 7bit headers in mails: now trashed
  - fixed zope part to cut subject and other field when they are too long to fit in db
  - removed year,pid from subject, added X-Achiver-ID header instead
  - moved some constants from config.py into archiver.py

* Version 1.1 - dec 16 2003
  - Added month (number) to path to avoid directories with large amount of files
  - Added support for quotafile to check per-email quota
  - Added traceback when xmlrpc raises ProtocolError
  - Added Zope/Filesystem backend for mails, in future this part will be enanched

* Version 1.1b - mar 6 2004
  - Added whitelist array to avoid archiving system mails (root/postmaster)
