from struct import unpack
import datetime as dt
import uuid


vhd = 'static.2.vhd'

with open(vhd, 'rb') as f:
    #
    # Footer
    #
    f.seek(-512, 2)
    footer = f.read(512)
    assert len(footer) == 512, 'incomplete tail footer'

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
    if footer_offset != 0xFFFFFFFFFFFFFFFF:
        print('Offset: ' + str(footer_offset))
    print('Modified: ' + str(dt.datetime.fromtimestamp(946674000 + ts)))
    print('Creator: ' + creator.decode())
    print('Size: ' + str(disk_size//1024//1024) + 'MB')
    print('Type: ' + str(type_))
    print('Saved: ' + (not saved and 'no' or 'yes'))
    print('GUID: ' + str(uuid.UUID(bytes=guid)))

    assert footer_magic == b'conectix', 'bad footer magic'
    assert features == b'\x00\x00\x00\x02', 'features unimplemented'
    assert (footer_ver_major, footer_ver_minor) == (1, 0), 'only 1.0 version is supported'
    assert disk_size == data_size, 'data size is not equal to disk size'
