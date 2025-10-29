# `analyzer.py` 실행 결과 예시

이 문서는 `analyzer.py` 스크립트의 각 분석 옵션에 대한 실행 결과 예시를 보여줍니다.

## `--superblock`

슈퍼블록의 주요 정보를 분석하고 출력합니다.

```
--- Superblock Analysis ('squashfs.img') ---
  s_magic    : 0x73717368
  inode_count : 2586
  block_size : 65536 bytes
  compression_id : 4 (1:gzip, 2:lzma, 3:lzo, 4:xz, 6:zstd)
  flags         : 0x6c0
    -> Active Flags: xattr uncompressed, no compression options

--- Table Start Addresses ---
  inode_table_start       : 0xdc61f2
  directory_table_start   : 0xdcb7e4
  id_table_start          : 0xdd34a0
  fragment_table_start    : 0xdd2124
  xattr_id_table_start    : 0xffffffffffffffff

--- Other Info ---
  filesystem version        : 4.0
  creation time (mkfs_time)  : 2021-10-22 17:21:06
  root inode reference   : 0x515415dc
```

## `--root-inode`

루트 아이노드가 포함된 메타데이터 블록을 찾아 압축을 해제하고, 루트 아이노드의 기본 정보를 보여줍니다.

```
--- Root Inode Block Analysis ('squashfs.img') ---
  root_inode_ref: 0x515415dc
  -> metadata block offset: 0x5154
  -> inode offset in block: 0x15dc
  -> seeking to inode table block position: 0xdcb346
  -> block decompressed successfully (5628 bytes)

--- Root Inode Data Obtained ---
  inode type: 1 (DIR)
  root inode data (first 16 bytes): 0100ed010000000049216861cf000000
```

## `--root-dir`

루트 디렉토리(`/`)에 포함된 파일 및 디렉토리 목록을 파싱하여 출력합니다.

```
--- Root Directory Content Analysis ('squashfs.img') ---
  -> Found 2 entries in root directory.

--- [ / ] Directory Contents ---
  [0] bin                  (Type: DIR, Inode: 47)
  [1] dev                  (Type: DIR, Inode: 45)
```
