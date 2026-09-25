# cheerdot2-mouse-custom

CheerDots2 마우스 M버튼 커스터마이저 (Windows). PodMouse 본체는 수정하지 않습니다.

## 동작 원리 (리버스 엔지니어링 결과)

- M버튼은 표준 HID 키가 아니라 벤더 패킷(`key 0x51`, BLE)만 보냅니다.
  3초 홀딩에도 패킷 1개라 짧게/길게 구분은 **불가능**, 횟수로만 구분됩니다.
- PodMouse가 `0x51`을 받아 포인터 스타일 순환에 사용하므로, 이 도구는
  스타일을 단일(`-1`)로 묶어 순환을 무력화한 뒤 PodMouse 로그의 눌림을 보고
  지정 동작을 `SendInput` 등으로 대신 실행합니다.
- `mKeyShort/Long_function` 설정은 BLE 연결에서 발화하지 않습니다 (로그 64회 전수 확인).

## 요구사항

- Windows 10/11, Python 3.8+ (python.org 빌드, tkinter 포함)
- CheerDots2 드라이버(PodMouse) 설치 + 블루투스 페어링 + 실행 중
- `pip install websockets` (install.bat이 자동 설치)

## 설치

1. 릴리스 ZIP 다운로드 후 압축 해제 (또는 본 저장소 클론)
2. `install.bat` 실행 (관리자 권한 불필요)
3. PodMouse 실행 확인 후 도우미 창이 뜹니다

## 사용법

- **2번클릭** 행: M 누를 때마다 실행
- 종류:
  - `단일키`: 뒤 드롭다운에서 선택 (win, ctrl, alt, del, F1~F12, 방향키...)
  - `키조합`: 입력창 클릭 후 키를 직접 누름 (예: Ctrl+A)
  - `CMD 명령`: 명령어 (예: `notepad`, `calc`)
  - `프로그램 실행`: 찾기... 버튼으로 exe/bat 선택 (URL 가능)
  - `PodMouse 기능`: 번호 선택 (11 Enter, 18 창전환, 27 계산기...)
- `적용`: 저장 + 감시 켜짐 + 원래 포인터변환 억제(-1)
- `테스트`: 지금 설정 바로 실행
- `원복(-1,4,2)`: 포인터 순환 복구 + 감시 끄기

자세한 안내와 제약 사항은 `README.txt` 참고.
<img width="1777" height="1035" alt="image" src="https://github.com/user-attachments/assets/781a62c9-20c9-4dbf-9327-a6a96cc12d74" />

## 파일

| 파일 | 설명 |
|---|---|
| `cheer_double.py` | 메인 (M 감시 + 실행, pythonw 상주) |
| `cheer_physical.py` | 보조 (포인터 색/반경 설정, PodMouse 공식 API 경유) |
| `start_cheer_double.bat` | 실행기 |
| `install.bat` / `uninstall.bat` | 설치 / 제거 |
