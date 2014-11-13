import os
import logging



from pydoop.hdfs.core.api import CoreHdfsFs as CoreFsApi
from pydoop.hdfs.core.api import CoreHdfsFile as CoreFileApi

from pydoop.hdfs.common import BUFSIZE
from pydoop.hdfs.core.bridged.common import wrap_class_instance
from pydoop.hdfs.core.bridged.common import wrap_class
from pydoop.hdfs.core.bridged.common import wrap_array

logging.basicConfig(level=logging.INFO)

BUFFER_SIZE_CONFIG_PROPERTY = "io.file.buffer.size"
REPLICATION_CONFIG_PROPERTY = "dfs.replication"
BLOCKSIZE_CONFIG_PROPERTY = "dfs.blocksize"



class JavaClassName(object):
    """
    Wraps the set of java classes used for implementing the Hadoop HDFS
    """
    VersionInfo = "org.apache.hadoop.util.VersionInfo"
    Configuration = 'org.apache.hadoop.conf.Configuration'
    FileSystem = "org.apache.hadoop.fs.FileSystem"
    Path = "org.apache.hadoop.fs.Path"
    FsPermission = "org.apache.hadoop.fs.permission.FsPermission"
    FileUtil = "org.apache.hadoop.fs.FileUtil"
    URI = "java.net.URI"
    String = "java.lang.String"
    ByteBuffer = "java.nio.ByteBuffer"
    Byte = "java.lang.Byte"
    Long = "java.lang.Long"
    DataOutputStream = "java.io.DataOutputStream"
    BufferedOutputStream = "java.io.BufferedOutputStream"
    ByteArrayOutputStream = "java.io.ByteArrayOutputStream"


def get_jpath(path):
    if not path:
        raise ValueError("Empty path")
    return wrap_class_instance(JavaClassName.Path, path)


class CoreHdfsFs(CoreFsApi):

    def __init__(self, host, port=0, user=None, groups=None):
        self._host = host
        self._port = port
        self._user = user
        self._groups = groups
        self._logger = logging.getLogger(self.__class__.__name__)
        self._configuration = wrap_class_instance(JavaClassName.Configuration, True)
        self._connect()


    def __eq__(self, other):
        return type(self) == type(other) and self._fs.toString() == other._fs.toString()

    def _connect(self):

        jfs_cl = wrap_class(JavaClassName.FileSystem)

        if self._host is None or self._host == '':
            self._fs = jfs_cl.getLocal(self._configuration)

        elif self._host == 'default' and self._port == 0:
            self._fs_uri = jfs_cl.getDefaultUri(self._configuration)
            if self._user:
                self._fs = jfs_cl.get(self._fs_uri, self._configuration, self._user)
            else:
                self._fs = jfs_cl.get(self._fs_uri, self._configuration)

        else:
            uri_str = "hdfs://%s:%s" % (self._host, self._port)
            juri_cl = wrap_class(JavaClassName.URI)
            self._fs_uri = juri_cl.create(uri_str)
            if self._user:
                self._fs = jfs_cl.get(self._fs_uri, self._configuration, self._user)
            else:
                self._fs = jfs_cl.get(self._fs_uri, self._configuration)


    def chmod(self, path, mode):
        jpath_ = get_jpath(path)
        jshort_cl = wrap_class("java.lang.Short")
        jpermission = wrap_class_instance(JavaClassName.FsPermission, mode)  # jshort_cl.valueOf(mode))
        self._fs.setPermission(jpath_, jpermission)

    def chown(self, path, user, group):
        if (user is None or user == '') and (group is None or group == ''):
            raise Exception("Both owner and group cannot be null in chown")

        jpath = get_jpath(path)
        old_path_info = self._get_jpath_info(jpath)
        if user is None or user == '':
            user = old_path_info['owner']
        if group is None or group == '':
            group = old_path_info['group']
        self._fs.setOwner(jpath, user, group)

    def exists(self, path):
        return self._fs.exists(get_jpath(path))

    def get_capacity(self):
        return self._fs.getRawCapacity()

    def close(self):
        self._fs.close()

    def _copy_helper(self, from_path, to_hdfs, to_path, delete_source):
        src_path = get_jpath(from_path)
        dst_path = get_jpath(to_path)

        jfileUtil = wrap_class(JavaClassName.FileUtil)
        return jfileUtil.copy(self._fs, src_path, to_hdfs._fs, dst_path, delete_source, self._configuration)

    def copy(self, from_path, to_hdfs, to_path):
        self._copy_helper(from_path, to_hdfs, to_path, False)

    def create_directory(self, path):
        return self._fs.mkdirs(get_jpath(path))

    def delete(self, path, recursive=True):
        jpath = get_jpath(path)
        self._fs.delete(jpath, recursive)

    def get_user(self):
        return self._user

    def get_path_info(self, path):
        jpath = get_jpath(path)
        return self._get_jpath_info(jpath)

    def get_default_block_size(self):
        return self._fs.getDefaultBlockSize()

    def get_host(self):
        return self._host

    def get_hosts(self, path, start, length):
        result = []
        jpath = get_jpath(path)
        jstatus = self._get_jfilestatus(jpath)
        jblock_locations = self._fs.getFileBlockLocations(jstatus, start, length)
        for jblock_location in jblock_locations:
            result.append([str(x) for x in jblock_location.getHosts()])
        return result

    def get_working_directory(self):
        return self._fs.getWorkingDirectory().toString()

    def get_port(self):
        return self._port

    def get_used(self):
        return self._fs.getRawUsed()

    def set_working_directory(self, path):
        jpath = get_jpath(path)
        self._fs.setWorkingDirectory(jpath)

    def move(self, from_path, to_hdfs, to_path):
        self._copy_helper(from_path, to_hdfs, to_path, True)

    def set_replication(self, path, replication):
        jpath = get_jpath(path)
        self._fs.setReplication(jpath, replication)

    def list_directory(self, path):
        jpath = get_jpath(path)
        if not self._fs.exists(jpath):
            raise IOError("Path %s does not exist" % path)

        jsubstatus = self._fs.listStatus(jpath)
        result = []
        for jstatus in jsubstatus:
            result.append(self._get_jpath_info(jstatus.getPath(), jstatus))
        return result

    def rename(self, from_path, to_path):
        jfrom_path = get_jpath(from_path)
        jto_path = get_jpath(to_path)
        self._fs.rename(jfrom_path, jto_path)

    def open_file(self, path, flags=0, buff_size=0, replication=1, blocksize=0, readline_chunk_size=16384):

        O_ACCMODE = os.O_RDONLY | os.O_RDWR | os.O_WRONLY
        accmode = flags & O_ACCMODE

        # check whether you are trying to open the file in 'rw' mode
        if accmode != os.O_WRONLY and accmode != os.O_RDONLY:
            if accmode == os.O_RDWR:
                raise IOError("Cannot open an hdfs file in O_RDWR mode")
            else:
                raise IOError("Cannot open an hdfs file in mode %s" % accmode)

        if (flags & os.O_CREAT) and (flags & os.O_EXCL):
            self._logger.warn("hdfs does not truly support O_CREATE && O_EXCL")

        # read the 'buffer size' property from the Configuration
        if not buff_size:
            buff_size = int(self._configuration.getInt(BLOCKSIZE_CONFIG_PROPERTY, 4096))

        # read the replication property from the Configuration (needed only for write-only mode)
        if (accmode == os.O_WRONLY) and (flags & os.O_APPEND) == 0 and not replication:
            replication = self._configuration.getInt(REPLICATION_CONFIG_PROPERTY, 1)

        # the Java path
        jpath = get_jpath(path)

        stream = None
        stream_type = None
        try:
            if accmode == os.O_RDONLY:
                stream = self._fs.open(jpath, buff_size)
                stream_type = CoreHdfsFile._INPUT
                self._logger.debug("File opened in read mode")

            elif accmode == os.O_WRONLY and flags & os.O_APPEND:
                stream = self._fs.append(jpath)
                stream_type = CoreHdfsFile._OUTPUT
                self._logger.debug("File opened in append mode")

            else:
                boolean_overwrite = True

                if not blocksize:
                    blocksize = self._fs.getDefaultBlockSize(jpath)

                stream = self._fs.create(jpath, boolean_overwrite, buff_size, replication, blocksize)
                stream_type = CoreHdfsFile._OUTPUT
                self._logger.debug("File opened in write mode")

        except Exception, e:
            raise IOError(e.message)

        return CoreHdfsFile(flags, stream, stream_type)

    def utime(self, path, mtime, atime):
        jpath = get_jpath(path)
        self._fs.setTimes(jpath, mtime, atime)

    def _get_jpath_info(self, jpath, jstatus=None):
        info = dict()

        if jstatus is None:
            try:
                jstatus = self._fs.getFileStatus(jpath)
                jpath = jstatus.getPath()
            except Exception:
                raise IOError

        info['name'] = jpath.toString()

        if self._fs.isDirectory(jpath):
            info['kind'] = 'directory'
        else:
            info['kind'] = 'file'

        info['group'] = jstatus.getGroup()

        jlong_cl = wrap_class(JavaClassName.Long)
        info['last_mod'] = jlong_cl.valueOf(jstatus.getModificationTime()).intValue()
        info['last_access'] = jlong_cl.valueOf(jstatus.getAccessTime()).intValue()

        info['replication'] = jstatus.getReplication()
        info['owner'] = jstatus.getOwner()
        info['permissions'] = jstatus.getPermission().toShort()
        info['block_size'] = self._fs.getBlockSize(jpath)
        info['path'] = jstatus.getPath().toString()
        info['fs_uri'] = self._fs.getUri().toString()
        info['depth'] = jpath.depth()
        info['size'] = jstatus.getLen()
        info['absolute'] = True if jpath.isAbsolute() else False
        parent = jpath.getParent()
        if parent:
            info['parent'] = parent.getName()

        return info

    def _get_jfilestatus(self, path):
        jpath = path
        if isinstance(path, str):
            jpath = get_jpath(path)
        return self._fs.getFileStatus(jpath)

    def _get_jfile_utils(self):
        return wrap_class(JavaClassName.FileUtil)


class CoreHdfsFile(CoreFileApi):

    _INPUT = 0
    _OUTPUT = 1

    def __init__(self, mode, stream, stream_type=_INPUT):
        self._mode = mode
        self._stream = stream
        self._stream_type = stream_type

        if stream_type == self._OUTPUT:
            self._buffered_stream = wrap_class_instance(JavaClassName.BufferedOutputStream, self._stream)
            self._jbytearray = wrap_array("byte")

    def available(self):
        if not self._stream or self._stream_type != self._INPUT:
            return -1
        return int(self._stream.available())

    def get_mode(self):
        return self._mode

    def close(self):
        if not self._stream:
            raise IOError
        try:
            self._stream.close()
        except Exception, e:
            raise IOError(e.message)

    def write_chunk(self, chunk):
        return self._write(chunk.value, len(chunk.value))

    def write(self, data):
        return self._write(data, len(data))

    def _write(self, data, length=None):
        if not self._stream or self._stream_type != self._OUTPUT:
            raise IOError

        if length < 0:
            raise IOError

        #current_size = self._stream.size()

        if length > 0:
            self._stream.write(self._jbytearray(data))

        #written = self._stream.size() - current_size
        #return written
        return length

    def tell(self):
        if not self._stream:
            raise IOError
        return long(self._stream.getPos())

    def seek(self, position):
        if not self._stream or self._stream_type != self._INPUT:
            raise IOError
        self._stream.seek(long(position))

    def read(self, length=-1):
        if not self._stream or self._stream_type != self._INPUT:
            raise IOError
        try:

            if length == -1:
                length = BUFSIZE

            jbyte_buffer_class = wrap_class(JavaClassName.ByteBuffer)
            bb = jbyte_buffer_class.allocate(length)
            buf = bb.array()
            read = self._stream.read(buf)
            if read == -1:
                return ""

            #return wrap_class_instance(JavaClassName.String, buf).toString()[:read] OLD Impl
            return ''.join( map(lambda x: chr((x+256)%256), buf[:read])) #FIXME: low performances

        except Exception, e:
            raise IOError(e.message)

    def read_chunk(self, chunk):
        if not self._stream or self._stream_type != self._INPUT:
            raise IOError
        try:

            length = len(chunk)
            jbyte_buffer_class = wrap_class(JavaClassName.ByteBuffer)
            bb = jbyte_buffer_class.allocate(length)
            buf = bb.array()
            read = self._stream.read(buf)
            if read == -1:
                return ""
            chunk.value = ''.join( map(lambda x: chr((x+256)%256), buf[:read])) #FIXME: low performances
            #chunk.value = wrap_class_instance(JavaClassName.String, buf).toString()[:read]
            return read

        except Exception, e:
            raise IOError(e.message)

    def pread(self, position, length):
        if not self._stream or self._stream_type != self._INPUT:
            raise IOError
        try:

            if length == -1:
                length = BUFSIZE

            jbyte_buffer_class = wrap_class(JavaClassName.ByteBuffer)
            bb = jbyte_buffer_class.allocate(length)
            buf = bb.array()
            read = self._stream.read(long(position), buf, 0, length)
            #return wrap_class_instance(JavaClassName.String, buf).toString()[:read] OLD Impl
            return ''.join( map(lambda x: chr((x+256)%256), buf[:read])) #FIXME: low performances

        except Exception, e:
            raise IOError(e.message)

    def pread_chunk(self, position, chunk):
        if not self._stream or self._stream_type != self._INPUT:
            raise IOError
        try:

            length = len(chunk)
            jbyte_buffer_class = wrap_class(JavaClassName.ByteBuffer)
            bb = jbyte_buffer_class.allocate(length)
            buf = bb.array()
            read = self._stream.read(long(position), buf, 0, length)
            chunk.value = ''.join( map(lambda x: chr((x+256)%256), buf[:read])) #FIXME: low performances
            #chunk.value = wrap_class_instance(JavaClassName.String, buf).toString()
            return read

        except Exception, e:
            raise IOError(e.message)

    def flush(self):
        if not self._stream or self._stream_type != self._OUTPUT:
            raise IOError
        self._stream.flush()


