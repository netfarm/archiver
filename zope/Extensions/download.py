###
from os.path import join as path_join
BASEPATH  = '/mnt/archiver/archiver'
MOUNTPATH = '/mnt/dvd'

mime_types = {
    '\037\213'   : [ 'application/x-gzip',  'eml.gz'  ],
    'PK\003\004' : [ 'application/x-zip',   'eml.zip' ],
    'BZh'        : [ 'application/x-bzip2', 'eml.bz2' ],
    'Received:'  : [ 'message/rfc822',      'eml'     ]
    }

def guess_mime(data):
    for m in mime_types.keys():
        if data.startswith(m):
            return mime_types[m]
    return ['application/octet-stream', 'bin']

def download(self, year, pid, month, media, response,  REQUEST=None):
    if REQUEST is not None: return 'Bad request'

    filename = path_join(BASEPATH, year, month, pid)

    try:
        data = open(filename).read()
    except:
        try:
            filename = path_join(MOUNTPATH, 'archiver', year, month, pid)
            data = open(filename).read()
        except:
            raise Exception, 'Please mount media labeled %s on %s, then hit reload' % (media, MOUNTPATH)

    mime, ext = guess_mime(data[:16])
    filedname = '%s-%s.%s' % (year, pid, ext)

    response.setHeader('content-type', mime)
    response.setHeader('Content-Disposition', 'attachment; filename="%s"' % filedname)

    return data
