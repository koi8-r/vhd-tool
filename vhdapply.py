from sys import version_info, stdin, stdout
from os import fdopen, dup
from struct import unpack
from operator import itemgetter
import datetime as dt
import uuid


# version 1.2 tdbatmap: https://github.com/xapi-project/blktap/blob/master/include/vhd.h
# xxd -s $[2*1024*1024+1024] static.vhd | vim -


vhd = 'static_21EC8EC3-721F-4466-91CD-26B8431D2148.1.avhd'
PY3 = version_info >= (3, 0)

if not PY3:
    assert 0 > 1, 'Use python3 and fix byte iterations and remove this line from source code'



# todo
def ensure_write(f, b):
    assert f.mode == 'wb'
    assert len(b) == f.write(b)


# todo
def ensure_read(f, l):
    assert f.mode == 'rb'
    r = f.read(l)
    assert len(r) == l


with open(vhd, 'rb') as f, \
     open('_static.1.vhd', 'rb+') as of:
# with fdopen(dup(stdin.fileno()), 'rb') as f, \
#      fdopen(dup(stdout.fileno()), 'rb+') as of:

    assert f.mode == 'rb'
    assert of.mode == 'rb+'

    #
    # Footer mirror
    #
    footer = f.read(512)
    assert len(footer) == 512, 'incomplete starting footer'

    (footer_magic,
     features,
     footer_ver_major,
     footer_ver_minor,
     footer_offset,
     ts,
     creator,
     cver_major,
     cver_minor,
     chost,
     disk_size,
     data_size,
     cylinders, heads, sectors_per_track,
     type_,
     checksum,
     guid,
     saved) = unpack('>8s4sHHQL4sHH4sQQHccLL16sb',
                     footer[:85])

    print('Version: ' + '.'.join(str(v) for v in [footer_ver_major, footer_ver_minor]))
    print('Modified: ' + str(dt.datetime.fromtimestamp(946674000 + ts)))
    print('Creator: ' + creator.decode())
    print('Size: ' + str(disk_size//1024//1024) + 'MB')
    print('Saved: ' + (not saved and 'no' or 'yes'))
    print('GUID: ' + str(uuid.UUID(bytes=guid)))

    assert footer_magic == b'conectix', 'bad footer magic'
    assert features == b'\x00\x00\x00\x02', 'features unimplemented'
    assert (footer_ver_major, footer_ver_minor) == (1, 0), 'only 1.0 version is supported'
    assert footer_offset == 512, 'footer offset must be 512'
    assert disk_size == data_size, 'data size is not equal to disk size'
    assert type_ in [3, 4], 'only dynamic or differential hard disks are supported'

    #
    # Dynamic/Differential disk header
    #
    header = f.read(1024)
    assert len(header) == 1024, 'incomplete header'

    (header_magic,
     header_offset,
     block_table_offset,  # BAT
     header_ver_major,
     header_ver_minor,
     block_num,           # max BAT entries, disk_size/block_size, 512pad
     block_size,          # power of two multitude of the sector size, 2MB
     checksum,
     parent_guild,
     parent_ts,
     reserved,
     parent_name,
     ple                  # parent locator entries for diff disk
    ) = unpack('>8sQQHHLLL16sL4s512s192s',
               header[:768])

    bitmap_size = block_size//512//8  # 512pad
    print('Block table offset: ' + str(block_table_offset))
    print('Blocks number: ' + str(block_num))  # disk image of 2GB which uses 2MB blocks needs entries up to 1024 BAT, 1GB needs 512 BAT
    print('Block size: ' + str(block_size//1024//1024) + 'MB')
    print('Bitmap size: ' + str(bitmap_size) + 'B')
    print('Parent GUID: ' + str(uuid.UUID(bytes=parent_guild)))
    print('Parent modified: ' + str(dt.datetime.fromtimestamp(946674000 + parent_ts)))  # sum with hardcoded millenium timestamp
    print('Parent name: ' + parent_name.decode('utf-16be').strip('\x00'))

    assert header_magic == b'cxsparse', 'bad header magic'
    assert (header_ver_major, header_ver_minor) == (footer_ver_major, footer_ver_minor), 'only 1.0 version is supported'
    assert block_size == 2097152, 'only default 2MB block size is supported'  # power of two multitude of the sector size
    assert disk_size//block_size == block_num, 'incorrect number of blocks'

    # Differential disk parent locator entries
    for i in range(0, 8):
        # locator's descriptor
        (platform_code,
         data_space,
         data_size,
         reserved,
         data_offset
        ) = unpack('>4sLLLQ', ple[24*i:24*i+24])
        print('Locator: ' + str(i+1))
        print('  platform code: ' + platform_code.strip(b'\x00').strip(b'\x20').decode())
        print('  data space: ' + str(data_space) + 'u')
        print('  data size: ' + str(data_size))
        print('  data offset: ' + str(data_offset))
        if data_offset > 0:
            f.seek(data_offset)
            print('  data: ' + f.read(data_size).decode('utf-16le'))
        else:
            print('  data: null')

    #
    # BAT: Block address table
    #

    f.seek(block_table_offset)  # seek to BAT
    bat = []
    for _ in range(0, block_num):  # BAT iterate
        block_table_entry = unpack('>L', f.read(4))[0]
        if not block_table_entry == 0xffffffff:  # sparse
            block_offset = block_table_entry * 512  # offset in sectors
        else:
            block_offset = None
        bat.append(block_offset)

    print('BAT:\n' + '\n'.join('  '+str(_)+'B' for _ in bat if _ is not None))

    # todo: sort(broken) for stdin stream read without seeking
    # for bati, bate in sorted(enumerate(bat, 0), key=itemgetter(1)):
    for bati, bate in enumerate(bat):  # bate: 2Mb
        if bate is None:
            continue
        print("\r{}/{}".format(block_num, bati+1), end='')
        f.seek(bate)  # seek to block
        bitmap = f.read(bitmap_size)
        assert len(bitmap) == 512
        # todo: calculate offsets once
        for bmi, bme in enumerate(bitmap, 0):  # bme: 4KB
            assert bme in [255, 0], 'test non 4K reads and remove this line'  # bitmap element is always 0xff because of 4KB(8 bits x 512 sector size) I/O optimised writes
            # 512B I/O
            if bme != 255:
                for i in range(0, 8):  # bme each bit: 512B
                    if not not (bme << i & 128):
                        real_offset = block_size * bati + 8*512 * bmi + 512 * i  # 2M block sized offset + 512 sector size
                        sector = f.read(512)
                        assert len(sector) == 512
                        of.seek(real_offset)
                        assert 512 == of.write(sector)  # write!!!
                    else:
                        f.seek(512, 1)
            # skip 4KB
            elif bme == 0:
                f.seek(8 * 512, 1)
            # 4KB I/O
            else:
                real_offset = block_size * bati + 8*512 * bmi  # 2M block sized offset + 4k(8 bits x 512 sector size) 
                sector = f.read(8*512)
                assert 8*512 == 4096 == len(sector)
                of.seek(real_offset)
                assert 8*512 == of.write(sector)  # write!!!

    print()
    of.flush()
    print('success')
