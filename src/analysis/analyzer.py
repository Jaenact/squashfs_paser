
import struct
import sys
import pathlib
import zlib
import lzma
from datetime import datetime
import argparse

try:
    import zstandard
except ImportError:
    zstandard = None

# --- 1. 구조체 및 상수 정의 ---
SUPERBLOCK_FORMAT = '<IIIIIHHHHHHQQQQQQQQ'
SUPERBLOCK_SIZE = 96
METADATA_HEADER_FORMAT = '<H'
METADATA_HEADER_SIZE = 2
BASE_INODE_FORMAT = '<HHHHII'
BASE_INODE_SIZE = 16
DIR_INODE_FORMAT = '<IIHHI'
DIR_INODE_SIZE = 16
DIR_HEADER_FORMAT = '<III'
DIR_HEADER_SIZE = 12
DIR_ENTRY_FORMAT = '<HhHH'
DIR_ENTRY_SIZE = 8
EXT_DIR_INODE_FORMAT = '<IIIIHHI'
EXT_DIR_INODE_SIZE = 24

TYPE_MAP = {
    1: "DIR", 2: "FILE", 3: "SYMLINK", 4: "BLK_DEV",
    5: "CHAR_DEV", 6: "FIFO", 7: "SOCKET", 8: "EXT_DIR",
}

FLAG_DEFS = {
    0x0001: "inode uncompressed", 0x0002: "data block uncompressed", 0x0004: "deprecated",
    0x0008: "fragment uncompressed", 0x0010: "no deduplication", 0x0020: "export table exists",
    0x0040: "xattr uncompressed", 0x0080: "no compression options", 0x0100: "always-sparse",
}

# --- 2. 헬퍼 함수 ---

def decompress_block(compressed_data, compression_id):
    """압축 ID에 맞는 라이브러리로 압축을 해제합니다."""
    if compression_id == 1: return zlib.decompress(compressed_data)
    if compression_id == 4: return lzma.decompress(compressed_data)
    if compression_id == 6:
        if zstandard: return zstandard.ZstdDecompressor().decompress(compressed_data)
        else: raise Exception("Zstd(id 6) 'zstandard' library needed")
    raise Exception(f"Unsupported compression ID: {compression_id}")

def read_metadata_block(f, block_position, compression_id):
    """지정된 위치의 메타데이터 블록 1개를 읽고 압축을 해제하여 반환합니다."""
    f.seek(block_position)
    header_val = struct.unpack(METADATA_HEADER_FORMAT, f.read(METADATA_HEADER_SIZE))[0]
    is_compressed = not (header_val & 0x8000)
    data_size = header_val & 0x7FFF
    block_data = f.read(data_size)
    return decompress_block(block_data, compression_id) if is_compressed else block_data

# --- 3. 분석 함수 ---

def analyze_superblock(filename):
    """Superblock.py의 기능을 수행합니다."""
    print(f"--- Superblock Analysis ('{filename}') ---")
    try:
        with open(filename, 'rb') as f:
            data = f.read(SUPERBLOCK_SIZE)
        
        sb = struct.unpack(SUPERBLOCK_FORMAT, data)
        s_magic, inode_count, mkfs_time, block_size, _, comp_id, _, flags, _, v_maj, v_min, root_ref, _, id_start, xattr_start, inode_start, dir_start, frag_start, _ = sb

        print(f"  s_magic    : {hex(s_magic)}")
        if s_magic != 0x73717368: print("  >> warning: invalid SquashFS magic number")
        print(f"  inode_count : {inode_count}")
        print(f"  block_size : {block_size} bytes")
        print(f"  compression_id : {comp_id} (1:gzip, 2:lzma, 3:lzo, 4:xz, 6:zstd)")
        print(f"  flags         : {hex(flags)}")
        active_flags = [desc for bit, desc in FLAG_DEFS.items() if (flags & bit)]
        if active_flags: print(f"    -> Active Flags: {', '.join(active_flags)}")
        
        print("\n--- Table Start Addresses ---")
        print(f"  inode_table_start       : {hex(inode_start)}")
        print(f"  directory_table_start   : {hex(dir_start)}")
        print(f"  id_table_start          : {hex(id_start)}")
        print(f"  fragment_table_start    : {hex(frag_start)}")
        print(f"  xattr_id_table_start    : {hex(xattr_start)}")

        print("\n--- Other Info ---")
        print(f"  filesystem version        : {v_maj}.{v_min}")
        print(f"  creation time (mkfs_time)  : {datetime.fromtimestamp(mkfs_time)}")
        print(f"  root inode reference   : {hex(root_ref)}")

    except Exception as e:
        print(f"Error during superblock analysis: {e}")

def analyze_root_inode(filename):
    """root_inode.py의 기능을 수행합니다."""
    print(f"--- Root Inode Block Analysis ('{filename}') ---")
    try:
        with open(filename, 'rb') as f:
            sb_data = f.read(SUPERBLOCK_SIZE)
            _, _, _, _, _, comp_id, _, _, _, _, _, root_ref, _, _, _, inode_start, _, _, _ = struct.unpack(SUPERBLOCK_FORMAT, sb_data)

            block_offset = root_ref >> 16
            inode_offset = root_ref & 0xFFFF
            inode_block_pos = inode_start + block_offset

            print(f"  root_inode_ref: {hex(root_ref)}")
            print(f"  -> metadata block offset: {hex(block_offset)}")
            print(f"  -> inode offset in block: {hex(inode_offset)}")
            print(f"  -> seeking to inode table block position: {hex(inode_block_pos)}")

            decompressed_data = read_metadata_block(f, inode_block_pos, comp_id)
            print(f"  -> block decompressed successfully ({len(decompressed_data)} bytes)")

            root_inode_data = decompressed_data[inode_offset:]
            inode_type = struct.unpack('<H', root_inode_data[0:2])[0]
            print("\n--- Root Inode Data Obtained ---")
            print(f"  inode type: {inode_type} ({TYPE_MAP.get(inode_type, 'Unknown')})")
            print(f"  root inode data (first 16 bytes): {root_inode_data[0:16].hex()}")

    except Exception as e:
        print(f"Error during root inode analysis: {e}")

def analyze_root_inode_data():
    """root_inode_data.py의 기능을 수행합니다 (테스트 데이터 사용)."""
    print("--- Root Inode Data Parsing (using test data) ---")
    temp_hex_data = "0100ed0100000000049216861cf00000" + "c01900000200000025000c0001000000"
    root_inode_data = bytes.fromhex(temp_hex_data)
    
    try:
        base_data = root_inode_data[:BASE_INODE_SIZE]
        i_type, perms, _, _, mtime, i_num = struct.unpack(BASE_INODE_FORMAT, base_data)
        print("--- 1. Base Inode Header (16 bytes) ---")
        print(f"  inode type : {i_type} ({TYPE_MAP.get(i_type, 'Unknown')})")
        print(f"  permissions : {oct(perms)}")
        print(f"  modified time : {datetime.fromtimestamp(mtime)}")
        print(f"  inode number : {i_num}")

        if i_type == 1: # Basic Directory
            dir_data = root_inode_data[BASE_INODE_SIZE : BASE_INODE_SIZE + DIR_INODE_SIZE]
            d_start, nlink, f_size, d_offset, p_inode = struct.unpack(DIR_INODE_FORMAT, dir_data)
            print("\n--- 2. Basic Directory Inode (next 16 bytes) ---")
            print(f"  hard_link_count : {nlink}")
            print(f"  file size : {f_size}")
            print(f"  parent inode : {p_inode}")
            print("\n--- Next Step Pointer Obtained!---")
            print(f"  directory table block start offset : {hex(d_start)}")
            print(f"  directory block offset        : {hex(d_offset)}")
    except Exception as e:
        print(f"Error during inode data parsing: {e}")

def analyze_root_directory(filename):
    """root_directory.py의 기능을 수행합니다."""
    print(f"--- Root Directory Content Analysis ('{filename}') ---")
    try:
        with open(filename, 'rb') as f:
            # 1. 슈퍼블록 파싱
            sb_data = f.read(SUPERBLOCK_SIZE)
            _, _, _, _, _, comp_id, _, _, _, _, _, root_ref, _, _, _, inode_start, dir_start, _, _ = struct.unpack(SUPERBLOCK_FORMAT, sb_data)

            # 2. 루트 아이노드 파싱
            block_offset = root_ref >> 16
            inode_offset = root_ref & 0xFFFF
            inode_block_pos = inode_start + block_offset
            decompressed_inode_block = read_metadata_block(f, inode_block_pos, comp_id)
            
            base_inode_data = decompressed_inode_block[inode_offset : inode_offset + BASE_INODE_SIZE]
            inode_type, _, _, _, _, _ = struct.unpack(BASE_INODE_FORMAT, base_inode_data)

            if inode_type == 1: # Basic Directory
                dir_data = decompressed_inode_block[inode_offset + BASE_INODE_SIZE : inode_offset + BASE_INODE_SIZE + DIR_INODE_SIZE]
                dir_block_start, _, file_size, dir_block_offset, _ = struct.unpack(DIR_INODE_FORMAT, dir_data)
            elif inode_type == 8: # Extended Directory
                ext_dir_data = decompressed_inode_block[inode_offset + BASE_INODE_SIZE : inode_offset + BASE_INODE_SIZE + EXT_DIR_INODE_SIZE]
                _, file_size, dir_block_start, _, _, dir_block_offset, _ = struct.unpack(EXT_DIR_INODE_FORMAT, ext_dir_data)
            else:
                raise Exception(f"Root inode is not a directory (type: {inode_type})")

            # 3. 디렉터리 테이블 파싱
            dir_block_pos = dir_start + dir_block_start
            decompressed_dir_block = read_metadata_block(f, dir_block_pos, comp_id)
            
            header_start_offset = dir_block_offset
            header_data = decompressed_dir_block[header_start_offset : header_start_offset + DIR_HEADER_SIZE]
            count, _, header_inode_number = struct.unpack(DIR_HEADER_FORMAT, header_data)
            entry_count = count + 1

            print(f"  -> Found {entry_count} entries in root directory.")
            print("\n--- [ / ] Directory Contents ---")
            
            current_entry_offset = header_start_offset + DIR_HEADER_SIZE
            for i in range(entry_count):
                entry_data = decompressed_dir_block[current_entry_offset : current_entry_offset + DIR_ENTRY_SIZE]
                _, inode_off, e_type, name_size_m1 = struct.unpack(DIR_ENTRY_FORMAT, entry_data)
                
                name_len = name_size_m1 + 1
                name_start = current_entry_offset + DIR_ENTRY_SIZE
                name_end = name_start + name_len
                name = decompressed_dir_block[name_start:name_end].decode('utf-8')
                
                real_inode_num = header_inode_number + inode_off
                type_str = TYPE_MAP.get(e_type, f"UKN({e_type})")
                
                print(f"  [{i}] {name:<20} (Type: {type_str}, Inode: {real_inode_num})")
                current_entry_offset = name_end
    except Exception as e:
        print(f"Error during root directory analysis: {e}")


# --- 4. 메인 실행 로직 ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SquashFS Analysis Tool")
    parser.add_argument('filename', nargs='?', default=None, help="Path to the squashfs image file (required for most analyses)")
    parser.add_argument('--superblock', action='store_true', help="Analyze the superblock")
    parser.add_argument('--root-inode', action='store_true', help="Analyze the root inode block")
    parser.add_argument('--root-inode-data', action='store_true', help="Parse root inode data from a test hex string")
    parser.add_argument('--root-dir', action='store_true', help="Analyze the root directory contents")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    if args.root_inode_data:
        analyze_root_inode_data()
    
    if not args.filename:
        if args.superblock or args.root_inode or args.root_dir:
            print("Error: A filename is required for this analysis.", file=sys.stderr)
            parser.print_help(sys.stderr)
            sys.exit(1)
    else:
        if not pathlib.Path(args.filename).exists():
            print(f"Error: File not found at '{args.filename}'")
            sys.exit(1)

        if args.superblock:
            analyze_superblock(args.filename)
        
        if args.root_inode:
            analyze_root_inode(args.filename)

        if args.root_dir:
            analyze_root_directory(args.filename)
