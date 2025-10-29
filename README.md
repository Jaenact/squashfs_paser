# SquashFS Parser

SquashFS 이미지 파일의 파일 시스템을 분석하고 파일을 추출하는 파이썬 스크립트입니다.

## 프로젝트 구조

```
.
├── .gitignore
├── README.md
├── requirements.txt
├── squashfs.img  (분석 대상 파일, .gitignore에 포함됨)
├── output/       (추출 결과 폴더, .gitignore에 포함됨)
└── src/
    ├── parser.py
    ├── parser_with_ai.py
    └── analysis/
        └── analyzer.py
```

## 설정

1.  **저장소 복제**

    ```bash
    git clone <repository-url>
    cd squashfs_paser
    ```

2.  **가상환경 생성 및 활성화**

    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    .\venv\Scripts\activate  # Windows
    ```

3.  **필요 라이브러리 설치**

    ```bash
    pip install -r requirements.txt
    ```

4.  **분석 대상 파일**

    프로젝트 루트 디렉토리에 분석할 `squashfs.img` 파일을 위치시킵니다.

## 사용법

### 파일 시스템 추출

두 가지 버전의 파서 스크립트를 제공합니다.

*   **기본 파서 (`parser.py`)**: XZ 압축 방식만 지원합니다.
    ```bash
    python src/parser.py squashfs.img
    ```

*   **AI 확장 파서 (`parser_with_ai.py`)**: GZIP, LZMA, LZO, XZ, LZ4, ZSTD 등 다양한 압축 방식을 지원합니다.
    ```bash
    python src/parser_with_ai.py squashfs.img
    ```

실행 후, 추출된 파일은 `output/` 디렉토리에 저장됩니다.

### 구조 분석

`analyzer.py` 스크립트를 사용하여 SquashFS 이미지의 특정 부분을 분석할 수 있습니다.

*   **슈퍼블록 분석**:
    ```bash
    python src/analysis/analyzer.py --superblock squashfs.img
    ```
*   **루트 아이노드 분석**:
    ```bash
    python src/analysis/analyzer.py --root-inode squashfs.img
    ```
*   **루트 디렉토리 내용 분석**:
    ```bash
    python src/analysis/analyzer.py --root-dir squashfs.img
    ```

## 스크립트 설명

*   **`src/parser.py`**: SquashFS 이미지 파일을 파싱하고 파일 시스템을 복구하는 기본 스크립트입니다.
*   **`src/parser_with_ai.py`**: 다양한 압축 알고리즘을 지원하도록 개선된 버전의 스크립트입니다.
*   **`src/analysis/analyzer.py`**: SquashFS의 슈퍼블록, 아이노드, 디렉토리 구조 등 특정 부분을 분석하기 위한 통합 분석 도구입니다.
