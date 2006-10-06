#!/usr/bin/env python
# -*- Mode: Python; tab-width: 4 -*-
#
# Netfarm Mail Archiver - release 2
#
# Copyright (C) 2005-2006 Gianni Giaccherini <jacketta@netfarm.it>
# Copyright (C) 2005-2006 NetFarm S.r.l.  [http://www.netfarm.it]
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
## @file backend_vfsimage.py
## Virtual Filesystem Storage only Backend

__doc__ = '''Netfarm Archiver - release 2.0.0 - Virtual Filesystem backend'''
__version__ = '2.0.0'
__all__ = [ 'Backend' ]

driver_map = { 'psql': 'psycopg' }

#vfs_image_size = (4*1024*1024)
vfs_image_size = 4
dir_size_fs = '.img_size'

from archiver import *
from sys import exc_info
from os import popen, path, access, makedirs, system, lstat, F_OK, R_OK, W_OK

##
class BadStorageDir(Exception):
    """BadStorageDir Bad Storage directory in config file"""
    pass

class Backend(BackendBase):
    """Filesystem Backend Class

    Stores emails on filesystem"""
    def __init__(self, config, stage_type, ar_globals):
        """The constructor"""
        self.config = config
        self.type = stage_type
        if self.type != 'storage':
            raise StorageTypeNotSupported, self.type

        self.LOG = ar_globals['LOG']
        self.storage_prefix = config.get(self.type, 'storage_prefix')
        self.storagedir = config.get(self.type, 'storagedir')
        self.type_prec = 'archive'

        self.dir_vfs = dir_size_fs
        self.vfs_max_size = vfs_image_size
        
        try:
            self.img_size = long(open(self.storagedir + '/'+self.dir_vfs).read())
        except:
            self.img_size = 0
        
        dsn = config.get(self.type_prec,'dsn')
                                                 
        if dsn.count(':') != 4:
            raise BadConnectionString, dsn

        driver, username, password, host, dbname = dsn.split(':')
        self.driver = driver_map[driver] 

        self.dsn = "host=%s user=%s password=%s dbname=%s" % (host,
                                                              username,
                                                              password,
                                                              dbname)

        try:
            self.db_connect = getattr(__import__(self.driver, globals(), locals(), []), 'connect', None)
        except:
            self.db_connect = None
            
        if self.db_connect is None:
            raise Exception, 'Rdbms Backend: Driver not found or missing connect method'

        self.connection = None
        self.cursor = None

        try:
            self.connect_psql()
        except: pass

        self.LOG(E_ALWAYS, 'Rdbms Backend (%s) %s at %s' % (self.type, driver, host))



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

    def connect_psql(self):
        """make a connection to rdbms

        raises ConnectionError if fails"""
        self.close()
        error = None
        
        try:
            self.connection = self.db_connect(self.dsn)
        except:
            ## We can work without the db connection and call it when needed
            t, val, tb = exc_info()
            del tb
            error = format_msg(val)

        if error is not None:
            self.LOG(E_ERR, 'Rdbms Backend: connection to database failed: ' + error)
            raise ConnectionError, error

        ## Try to disable autocommit
        try:
            self.connection.autocommit(0) # FIXME - API is changed
        except:
            t, val, tb = exc_info()
            del t, tb
            error = format_msg(val)

        if error is not None:
            self.LOG(E_ERR, 'Rdbms Backend: cannot disable autocommit on the DB connection: ' + error)
            self.close()
            raise ConnectionError, error

        ## Check if connection has rollback method
        if not hasattr(self.connection, 'rollback'):
            self.LOG(E_ERR, 'Rdbms Backend: DB Connection doesn\'t provide a rollback method')
            self.close()
            raise ConnectionError, 'No rollback method'

        self.cursor = self.connection.cursor()
        self.LOG(E_ALWAYS, 'Storage Backend (%s): I\'ve got a cursor from the driver' % (self.type))


    ### Update db entry for the email #########
    def update_db_entry(self, data):
        query = 'UPDATE mail set image_path=\'%(image_path)s\' where pid=%(pid)d and year=%(year)d;' % {'image_path':self.storagedir, 'pid': data['pid'], 'year':data['year']}
        print query
        try:
            self.cursor.execute(query)
            self.cursor.execute('COMMIT;')
        except:
            try:
                self.connection.rollback()
            except: pass
            self.LOG(E_ERR, 'VFS Backend: query fails')

        return 1
    

    ## Gets mailpath and filename
    def get_paths(self, data):
        month = data['date'][1]

        if not access(self.storagedir, F_OK | R_OK | W_OK):
            raise BadStorageDir, self.storagedir

        self.LOG(E_ALWAYS, 'Filesystem Backend (%s) at %s ' % (self.type, self.storagedir))

        mailpath = path.join(self.storagedir, str(data['year']), str(month))
        filename = path.join(mailpath, str(data['pid']))
        return mailpath, filename


    def create_image(image_num, dir_prefix):
        out_file = dir_prefix + '/iso/'+image_num+'.img'
        
        mount_image = dir_prefix+'/img'+image_num
        result_dd = popen('dd if=/dev/zero of='+out_file+' bs=512k count=32').read()
        result_mkfs = popen('mke2fs -q -F -j -T news -L ArchiveImg -m 0 -O dir_index,sparse_super ' +out_file).read()

        result_mkdir = popen('mkdir -p '+ path.join(mount_image,image_num)).read()

        result_mount = popen(' mount -o loop '+ out_file+' '+ mount_image).read()
        return 1
        

        

    #### Create a new VFS image using year + month + day
    def manage_image(self, data):
        if len(str(data['date'][1])) < 2:
            month = '0'+str(data['date'][1])
        else:
            month = str(data['date'][1])

        new_image_num = str(data['year'])+month+str(data['date'][2])
        token = self.storagedir.split('/')
        prefix_dir = '/'+'/'.join(token[1:len(token)-3])
        print "PREFIX DIR = " + prefix_dir

        ### Unmount it, modify as ext2 and delete the mount_point #######
        token = self.storagedir.split('/')
        old_image_num = token[len(token)-1]
        print "Old_Image_Num = " + old_image_num

        old_image_path = '/'+'/'.join(token[1:len(token)-1])
        
        print "Old_Image_Path = " + old_image_path

        result = popen('umount '+old_image_path).read()

        result = popen('rm -rf '+old_image_path).read()

        result = popen('tune2fs -O ^has_journal ' +prefix_dir+'/iso/'+old_image_num+'.img').read()


        

        ### Create New Image #######
        print "Check Image_Name = " + prefix_dir + '/iso/'+new_image_num+'.img'
        try:
            lstat(prefix_dir + '/iso/'+new_image_num+'.img')
            new_image_num = new_image_num+'_1'
        except:
            pass
        
        resul = popen('/usr/local/bin/New_Build_Image.sh '+new_image_num+' '+prefix_dir).read()

        image_prefix_dir_str = '/'+'/'.join(token[1:len(token)-2])
        
        result = ('mkdir -p '+image_prefix_dir_str + '/'+new_image_num+'/'+new_image_num).read()
        
        return image_prefix_dir_str + '/'+new_image_num +'/'+new_image_num


    ## Storage on filesystem
    def process(self, data):
        
        mailpath, filename = self.get_paths(data)
        ## First check integrity
        error = None
        if not access(mailpath, F_OK | R_OK | W_OK):
            error = 'No access to mailpath'
            try:
                makedirs(mailpath, 0700)
                error = None
            except:
                t, val, tb = exc_info()
                del tb
                error = '%s: %s' % (t, val)
                self.LOG(E_ERR, 'Filesystem Backend: Cannot create storage directory: ' + str(val))

        if error is not None:
            return 0, 443, error

        try:
            #### Check if we can write to current image.
            #### Otherwise create new one
            try:
                fd = open(filename, 'wb')
                fd.write(data['mail'])
            except IOError:
                try:
                    self.storagedir = manage_image(data)
                    mailpath, filename = self.get_paths(data)
                    fd = open(filename, 'wb')
                    fd.write(data['mail'])
                except:
                    return 0, 443, 'Unable to Open New Image'

            fd.flush()
            fd.close()

            #### Update database entry for the email
            try:
                self.update_db_entry(data)
            except:
                self.LOG(E_ERR, 'Unable to open db for update ')
                return 0, 443, '%s: %s' % (t, val)

            self.LOG(E_TRACE, 'Filesystem Backend: wrote ' + filename)
            return BACKEND_OK

        except:
            t, val, tb = exc_info()
            del tb
            self.LOG(E_ERR, 'Filesystem Backend: Cannot write mail file: ' + str(val))
            return 0, 443, '%s: %s' % (t, val)

    #### Rewrite Configuration on Shutdown #####
    def shutdown(self):
        """Backend Shutdown callback"""
        print "Storagedir = " + self.storagedir
        self.config.set(self.type,'storagedir',self.storagedir)
        fd = open('/etc/archiver.conf','w')
        print 'Rewriting config'
        self.config.write(fd)
        fd.close()
        self.close()
        print 'Config rewritten'
        self.LOG(E_ALWAYS, 'Filesystem Backend (%s): shutting down' % self.type)
