import sys
import os
import lzma  # XZ (4), LZMA (2) 압축 해제를 위함
import gzip # GZIP (1) 압축 해제를 위함
import math
import traceback

# --- 추가된 라이브러리 (LZO, LZ4, ZSTD) ---
try:
    import lzo       # LZO (3)
    import lz4.frame # LZ4 (5)
    import zstandard as zstd # ZSTD (6)
    print("--- 모든 압축 라이브러리 (gzip, lzma, lzo, lz4, zstd) 로드 완료 ---")
except ImportError as e:
    print(f"[경고] {e}")
    print("  일부 압축 형식이 지원되지 않을 수 있습니다.")
    print("  (해결: pip install python-lzo lz4 zstandard)")
    lzo = None
    lz4 = None
    zstd = None

# --- 1. 슈퍼블럭 파싱 함수 ---
def parse_superblock(f):
    """
    슈퍼블록 96바이트 읽고, 파싱된 정보를 딕셔너리로 반환
    """
    print("--- 1. 슈퍼블럭 파싱 ---")
    f.seek(0)
    sb = {} 
    
    sb['magic'] = int.from_bytes(f.read(4), 'little')

    if sb['magic'] != 0x73717368:
        print("SquashFS 매직 넘버 오류 발생")
        return
    
    sb['inode_count'] = int.from_bytes(f.read(4), 'little')
    sb['modification_time'] = int.from_bytes(f.read(4), 'little')
    sb['block_size'] = int.from_bytes(f.read(4), 'little')
    sb['fragment_entry_count'] = int.from_bytes(f.read(4), 'little')
    sb['compression_id'] = int.from_bytes(f.read(2), 'little') # <-- 중요!
    sb['block_log'] = int.from_bytes(f.read(2), 'little')
    sb['flags'] = int.from_bytes(f.read(2), 'little')
    sb['id_count'] = int.from_bytes(f.read(2), 'little')
    sb['version_major'] = int.from_bytes(f.read(2), 'little')
    sb['version_minor'] = int.from_bytes(f.read(2), 'little')
    sb['root_inode_ref'] = int.from_bytes(f.read(8), 'little')
    sb['bytes_used'] = int.from_bytes(f.read(8), 'little')
    sb['id_table_start'] = int.from_bytes(f.read(8), 'little')
    sb['xattr_id_table_start'] = int.from_bytes(f.read(8), 'little')
    sb['inode_table_start'] = int.from_bytes(f.read(8), 'little')
    sb['directory_table_start'] = int.from_bytes(f.read(8), 'little')
    sb['fragment_table_start'] = int.from_bytes(f.read(8), 'little')
    sb['export_table_start'] = int.from_bytes(f.read(8), 'little')

    # 파싱 후 기본 정보 출력
    compression_map = {1: "GZIP", 2: "LZMA", 3: "LZO", 4: "XZ", 5: "LZ4", 6: "ZSTD"}
    print(f"  SquashFS 버전: {sb['version_major']}.{sb['version_minor']}")
    print(f"  압축 방식: {compression_map.get(sb['compression_id'], 'Unknown')}") # <-- 변경
    print(f"  루트 아이노드 Ref: 0x{sb['root_inode_ref']:x}")
    print(f"  아이노드 테이블 시작: 0x{sb['inode_table_start']:x}")
    print(f"  디렉토리 테이블 시작: 0x{sb['directory_table_start']:x}")
    
    return sb

# --- 2. (신규) 압축 해제 헬퍼 함수 ---
def decompress_data(data, compression_id):
    """
    압축 ID에 따라 적절한 라이브러리를 사용해 압축 해제
    """
    try:
        if compression_id == 1: # GZIP
            return gzip.decompress(data)
        
        elif compression_id == 2: # LZMA
            # LZMA 라이브러리는 LZMA와 XZ를 모두 처리 가능
            return lzma.decompress(data)
        
        elif compression_id == 3: # LZO
            if lzo:
                return lzo.decompress(data)
            else:
                raise NotImplementedError("LZO 라이브러리가 설치되지 않았습니다 (pip install python-lzo)")
                
        elif compression_id == 4: # XZ
            return lzma.decompress(data)
        
        elif compression_id == 5: # LZ4
            if lz4:
                return lz4.frame.decompress(data)
            else:
                raise NotImplementedError("LZ4 라이브러리가 설치되지 않았습니다 (pip install lz4)")
            
        elif compression_id == 6: # ZSTD
            if zstd:
                return zstd.decompress(data)
            else:
                raise NotImplementedError("Zstandard 라이브러리가 설치되지 않았습니다 (pip install zstandard)")
        
        else:
            raise NotImplementedError(f"지원되지 않는 압축 ID: {compression_id}")
    
    except Exception as e:
        print(f"\n[오류] 압축 해제 실패: {e}")
        # traceback.print_exc() # 디버깅 시 주석 해제
        return b'' # 빈 바이트 반환

# --- 3. 메타데이터 읽기 함수 (수정됨) ---
def read_metablock(f, table_start_offset, block_ref, compression_id): # <-- compression_id 인자 추가
    """
    지정된 위치의 메타데이터를 읽고 압축을 해제하여 원본 데이터 반환
    """
    location = table_start_offset + block_ref
    f.seek(location)
        
    header_val = int.from_bytes(f.read(2), 'little')
    data_size = header_val & 0x7FFF
    is_compressed = not (header_val & 0x8000)
        
    if data_size == 0:
        return b''
        
    compressed_data = f.read(data_size)
        
    if is_compressed:
        # lzma.decompress(compressed_data) <-- (기존)
        return decompress_data(compressed_data, compression_id) # <-- (변경)
    else:
        return compressed_data
            

# --- 4. 프레그먼트 테이블 읽기 (수정됨) ---
def read_fragment_table(f, sb):
    """
    프래그먼트 테이블을 읽어 모든 프래그먼트 블록 엔트리 목록을 반환
    """
    print("--- 2. 프래그먼트 테이블 파싱 ---") # <-- 출력 번호 변경
    
    f.seek(sb['fragment_table_start'])
    fragment_count = sb['fragment_entry_count']
    compression_id = sb['compression_id'] # <-- (추가)

    metablock_pointer_count = math.ceil(fragment_count / 512)
    metablock_pointers = []
    for _ in range(metablock_pointer_count):
        metablock_pointers.append(int.from_bytes(f.read(8), 'little'))

    print(f"  프래그먼트 엔트리: {fragment_count}개, 메타블록 포인터: {len(metablock_pointers)}개")

    fragment_entries = [] 
    entries_read = 0
    
    for pointer in metablock_pointers:
        f.seek(pointer)
        header_val = int.from_bytes(f.read(2), 'little')
        data_size = header_val & 0x7FFF
        is_compressed = not (header_val & 0x8000)
        
        if data_size == 0:
            continue
            
        compressed_data = f.read(data_size)
        
        # data = lzma.decompress(compressed_data) if is_compressed else compressed_data <-- (기존)
        data = decompress_data(compressed_data, compression_id) if is_compressed else compressed_data # <-- (변경)

        offset = 0
        while offset < len(data) and entries_read < fragment_count:
            start = int.from_bytes(data[offset+0 : offset+8], 'little')
            size_val = int.from_bytes(data[offset+8 : offset+12], 'little')
            fragment_entries.append({'start': start, 'size_val': size_val})
            entries_read += 1
            offset += 16
        
    print("--- 프래그먼트 테이블 파싱 완료 ---")
    return fragment_entries

# --- 5. 핵심 로직: 단계별 함수 분리 (수정됨) ---

def extract_entry(f, sb, fragment_table, inode_ref, current_path, output_dir):
    """
    inode_ref를 받아 아이노드 '헤더'만 파싱해서 타입을 확인하고,
    타입에 맞는 '담당' 함수(process_directory, process_file)를 호출
    """
    
    # --- 1. 아이노드(Inode) 데이터 확보 ---
    inode_block_start_offset = (inode_ref >> 16) & 0xFFFFFFFF
    inode_offset_in_block = inode_ref & 0xFFFF
    
    # (기존) inode_data = read_metablock(f, sb['inode_table_start'], inode_block_start_offset)
    # (변경) compression_id 전달
    inode_data = read_metablock(f, sb['inode_table_start'], inode_block_start_offset, sb['compression_id'])

    # --- 2. 아이노드 공통 헤더 파싱 ---
    offset = inode_offset_in_block
    
    # 파싱 데이터가 부족할 경우 방어 코드
    if offset + 2 > len(inode_data):
        print(f"[오류] 아이노드 데이터 읽기 실패. offset: {offset}, data_len: {len(inode_data)}, ref: 0x{inode_ref:x}")
        return

    header_size = 16
    inode_type = int.from_bytes(inode_data[offset+0 : offset+2], 'little')
    inode_body_offset = offset + header_size
        
    full_local_path = os.path.join(output_dir, current_path)
    
    # 화면 출력을 위한 들여쓰기 및 이름 계산
    if current_path:
        depth = current_path.count(os.path.sep)
        indent = "  " * depth
        display_name = os.path.basename(current_path)
    else:
        indent = ""
        display_name = "/" # 루트 디렉토리

    # --- 3. 아이노드 유형별 처리 함수 호출 ---
    # 유형1 | 디렉토리 (Type 1, 8)
    if inode_type == 1 or inode_type == 8:
        print(f"{indent}[DIR]  {display_name}")
        os.makedirs(full_local_path, exist_ok=True)
        process_directory(f, sb, fragment_table, inode_type, inode_body_offset, inode_data, current_path, output_dir)
            
    # 유형2 | 파일 (Type 2, 9)
    elif inode_type == 2 or inode_type == 9:
        print(f"{indent}[FILE] {display_name} 추출 중..... -> ", end="")
        process_file(f, sb, fragment_table, inode_type, inode_body_offset, inode_data, full_local_path)

    # 유형3 | 심볼릭 링크 (Type 3, 10)
    elif inode_type == 3 or inode_type == 10:
        process_symlink(inode_type, inode_body_offset, inode_data, full_local_path, indent, display_name)

    # [D] 그 외
    else:
        print(f"{indent}[SKIP] 미지원 유형 ({inode_type}) : {display_name}")

def process_directory(f, sb, fragment_table, inode_type, inode_body_offset, inode_data, current_path, output_dir):
    """
    - 디렉토리 아이노드(1, 8)의 '본문'을 파싱
    - 디렉토리 테이블을 읽어옴
    - 자식 엔트리를 순회하며 'extract_entry'를 재귀 호출
    """
    
    # --- 1. 디렉토리 아이노드 '본문' 파싱 ---
    offset = inode_body_offset
    try:
        if inode_type == 1: # 기본 디렉토리
            dir_block_start = int.from_bytes(inode_data[offset+0 : offset+4], 'little')
            file_size = int.from_bytes(inode_data[offset+8 : offset+10], 'little') # u16
            dir_offset = int.from_bytes(inode_data[offset+10 : offset+12], 'little') # u16
            total_size_to_read = file_size - 3 
        else: # inode_type == 8 (확장 디렉토리)
            file_size = int.from_bytes(inode_data[offset+4 : offset+8], 'little') # u32
            dir_block_start = int.from_bytes(inode_data[offset+8 : offset+12], 'little') # u32
            dir_offset = int.from_bytes(inode_data[offset+18 : offset+20], 'little') # u16
            total_size_to_read = file_size - 3
    except IndexError:
        print(f"\n[오류] 디렉토리 아이노드 파싱 실패 (path: {current_path})")
        return

    # --- 2. 디렉토리 테이블 블록 읽기 ---
    # (기존) dir_data = read_metablock(f, sb['directory_table_start'], dir_block_start)
    # (변경) compression_id 전달
    dir_data = read_metablock(f, sb['directory_table_start'], dir_block_start, sb['compression_id'])
    
    bytes_read = 0
    current_entry_offset = dir_offset
    
    # --- 3. 자식 엔트리 순회 (while 루프) ---
    while bytes_read < total_size_to_read:
        try:
            # 3a. 디렉토리 헤더 (12 bytes) 읽기
            header_start_offset = current_entry_offset
            if header_start_offset + 12 > len(dir_data): break
                
            h_count = int.from_bytes(dir_data[header_start_offset+0 : header_start_offset+4], 'little') + 1
            h_start_block = int.from_bytes(dir_data[header_start_offset+4 : header_start_offset+8], 'little')
            
            current_entry_offset += 12
            bytes_read += 12
            
            # 3b. 'h_count' 개의 디렉토리 엔트리 읽기
            for i in range(h_count):
                if current_entry_offset + 8 > len(dir_data): break

                entry_start_offset = current_entry_offset
                e_offset = int.from_bytes(dir_data[entry_start_offset+0 : entry_start_offset+2], 'little')
                e_name_size = int.from_bytes(dir_data[entry_start_offset+6 : entry_start_offset+8], 'little') + 1
                name_start = entry_start_offset + 8
                
                if name_start + e_name_size > len(dir_data): break
                    
                name = dir_data[name_start : name_start + e_name_size].decode('utf-8', errors='ignore')
                entry_size_on_disk = 8 + e_name_size
                current_entry_offset += entry_size_on_disk
                bytes_read += entry_size_on_disk

                # --- 4. 재귀 호출 ---
                child_inode_ref = (h_start_block << 16) | e_offset
                child_path = os.path.join(current_path, name)
                
                extract_entry(f, sb, fragment_table, child_inode_ref, child_path, output_dir)
                
                if bytes_read >= total_size_to_read:
                    break
        
        except Exception as e:
            print(f"  [오류] 엔트리 파싱 중단 (path: {current_path}): {e}")
            # traceback.print_exc() # 디버깅 시 주석 해제
            break

def process_file(f, sb, fragment_table, inode_type, inode_body_offset, inode_data, full_local_path):
    """
    - 파일 아이노드(2, 9)의 '본문'을 파싱
    - 데이터 블록과 프래그먼트를 읽어 파일로 저장
    """
    offset = inode_body_offset
    compression_id = sb['compression_id'] # <-- (추가)
    
    # --- 1. 파일 아이노드 '본문' 파싱 ---
    try:
        if inode_type == 2: # 기본 파일
            blocks_start = int.from_bytes(inode_data[offset+0 : offset+4], 'little')
            fragment_block_index = int.from_bytes(inode_data[offset+4 : offset+8], 'little')
            block_offset = int.from_bytes(inode_data[offset+8 : offset+12], 'little')
            file_size = int.from_bytes(inode_data[offset+12 : offset+16], 'little')
            block_sizes_offset = offset + 16
        else: # inode_type == 9 (확장 파일)
            blocks_start = int.from_bytes(inode_data[offset+0 : offset+8], 'little') # u64
            file_size = int.from_bytes(inode_data[offset+8 : offset+16], 'little') # u64
            fragment_block_index = int.from_bytes(inode_data[offset+28 : offset+32], 'little')
            block_offset = int.from_bytes(inode_data[offset+32 : offset+36], 'little')
            block_sizes_offset = offset + 40
    except IndexError:
        print(f"\n[오류] 파일 아이노드 파싱 실패 (path: {full_local_path})")
        return

    if file_size == 0:
        try:
            with open(full_local_path, 'wb') as out_f: pass # 0바이트 파일 생성
            print("추출 완료 (0 바이트)")
        except OSError as e:
            print(f"\n[오류] 0바이트 파일 생성 실패: {e}")
        return

    has_fragment = (fragment_block_index != 0xFFFFFFFF)
    block_count = (file_size // sb['block_size']) if has_fragment else (math.ceil(file_size / sb['block_size']))

    try:
        with open(full_local_path, 'wb') as out_f:
            bytes_remaining_for_file = file_size
            current_data_offset = blocks_start
            
            # --- 2. '데이터 블록' 순회 ---
            for i in range(block_count):
                # 블록 크기 정보가 아이노드 데이터 범위를 벗어나는지 확인
                if block_sizes_offset + (i*4) + 4 > len(inode_data):
                    print(f"\n[오류] 블록 크기 정보 읽기 실패 (path: {full_local_path})")
                    break
                
                block_size_val = int.from_bytes(inode_data[block_sizes_offset + (i*4) : block_sizes_offset + (i*4) + 4], 'little')
                is_compressed = not (block_size_val & 0x1000000)
                block_size_on_disk = block_size_val & 0xFFFFFF
                
                if block_size_on_disk == 0:
                    decompressed_data = b'\x00' * sb['block_size']
                else:
                    f.seek(current_data_offset)
                    compressed_data = f.read(block_size_on_disk)
                    # (기존) decompressed_data = lzma.decompress(compressed_data) if is_compressed else compressed_data
                    decompressed_data = decompress_data(compressed_data, compression_id) if is_compressed else compressed_data # (변경)
                
                bytes_to_write = min(len(decompressed_data), bytes_remaining_for_file)
                out_f.write(decompressed_data[:bytes_to_write])
                bytes_remaining_for_file -= bytes_to_write
                current_data_offset += block_size_on_disk
            
            # --- 3. '프래그먼트' 처리 (파일의 꼬리) ---
            if has_fragment:
                fragment_size = file_size % sb['block_size']
                if fragment_size > 0:
                    # 프래그먼트 인덱스 유효성 검사
                    if fragment_block_index >= len(fragment_table):
                        print(f"\n[오류] 잘못된 프래그먼트 인덱스 (path: {full_local_path})")
                        return

                    frag_entry = fragment_table[fragment_block_index]
                    frag_start = frag_entry['start']
                    frag_size_val = frag_entry['size_val']
                    is_compressed = not (frag_size_val & 0x1000000)
                    frag_size_on_disk = frag_size_val & 0xFFFFFF
                    
                    f.seek(frag_start)
                    compressed_frag_block = f.read(frag_size_on_disk)
                    # (기존) decompressed_frag_block = lzma.decompress(compressed_frag_block) if is_compressed else compressed_frag_block
                    decompressed_frag_block = decompress_data(compressed_frag_block, compression_id) if is_compressed else compressed_frag_block # (변경)
                    
                    # 프래그먼트 데이터가 오프셋보다 작은 경우 방어
                    if block_offset > len(decompressed_frag_block):
                        print(f"\n[오류] 프래그먼트 오프셋 오류 (path: {full_local_path})")
                        return
                    
                    fragment_data = decompressed_frag_block[block_offset : block_offset + fragment_size]
                    
                    out_f.write(fragment_data)

        print("추출 완료")
    
    except OSError as e:
        print(f"\n[오류] 파일 쓰기 실패: {e}")
    except Exception as e:
        print(f"\n[오류] 파일 처리 중 알 수 없는 오류: {e}")
        # traceback.print_exc() # 디버깅 시 주석 해제


def process_symlink(inode_type, inode_body_offset, inode_data, full_local_path, indent, display_name):
    """
    - 심볼릭 링크 아이노드(3, 10)의 '본문'을 파싱
    - 원본 경로를 읽어 링크를 생성
    """
    offset = inode_body_offset
    try:
        if inode_type == 3: # 기본 심볼릭 링크
            target_size = int.from_bytes(inode_data[offset+4 : offset+8], 'little')
            target_path_offset = offset + 8
        else: # inode_type == 10 (확장 심볼릭 링크)
            target_size = int.from_bytes(inode_data[offset+4 : offset+8], 'little')
            target_path_offset = offset + 8
        
        if target_path_offset + target_size > len(inode_data):
            print(f"\n[오류] 심볼릭 링크 경로 파싱 실패 (path: {full_local_path})")
            return

        target_path = inode_data[target_path_offset : target_path_offset + target_size].decode('utf-8', errors='ignore')
    except IndexError:
        print(f"\n[오류] 심볼릭 링크 아이노드 파싱 실패 (path: {full_local_path})")
        return
    
    print(f"{indent}[SYMLINK] {display_name} -> {target_path}")
    
    try:
        # 심볼릭 링크 생성 시도 전, 대상 파일이 이미 존재하는지 확인 (예: 디렉토리)
        if os.path.exists(full_local_path) or os.path.lexists(full_local_path):
            os.remove(full_local_path)
        
        os.symlink(target_path, full_local_path)
    except OSError as e:
        print(f"  {indent}[경고] 심볼릭 링크 생성 실패 (권한 문제일 수 있음): {e}")
    except NotImplementedError:
        print(f"  {indent}[경고] 이 시스템에서 심볼릭 링크를 지원하지 않습니다.")
        # 링크 대신 텍스트 파일로 저장
        try:
            with open(full_local_path + ".symlink.txt", "w", encoding="utf-8") as f_link:
                f_link.write(target_path)
        except OSError as e_txt:
            print(f"  {indent}[경고] 링크 대체 텍스트 파일 생성 실패: {e_txt}")

# --- 6. 메인 실행 부분 ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python extract_squashfs.py [SquashFS 파일 경로]")
        sys.exit(1)
        
    file_to_parse = sys.argv[1]
    output_dir = "./output"
    
    if not os.path.exists(file_to_parse):
        print(f"[오류] 파일을 찾을 수 없습니다: {file_to_parse}")
        sys.exit(1)
    
    print(f"SquashFS 파일: {file_to_parse}")
    print(f"추출 위치: {output_dir}")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    f = None
    try:
        # 1. 파일 열기
        f = open(file_to_parse, 'rb')
        
        # 2. 슈퍼블럭 파싱
        sb = parse_superblock(f)
        
        # 3. 프래그먼트 테이블 파싱
        fragment_table = read_fragment_table(f, sb)
        
        # 4. root node부터 재귀 추출 시작
        print("\n--- 3. 파일 시스템 순회 (재귀 시작) ---")
t
        extract_entry(f, sb, fragment_table, sb['root_inode_ref'], "", output_dir)
        
        print("\n--- 4. 추출 완료 ---")
    
    except FileNotFoundError:
        print(f"[오류] 입력 파일 '{file_to_parse}'를 찾을 수 없습니다.")
    except PermissionError:
        print(f"[오류] 파일/디렉토리 권한이 없습니다.")
    except Exception as e:
        print(f"\n[치명적 오류] 스크립트 실행 중단: {e}")
        traceback.print_exc()
    finally:
        if f:
            f.close()
            print("(파일 핸들 닫힘)")