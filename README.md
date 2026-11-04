# course-material-sync

[![CI](https://github.com/jhlee1020lee/course-material-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/jhlee1020lee/course-material-sync/actions/workflows/ci.yml)

Canvas LMS의 강의 파일을 내려받고, 내용 변경과 로컬 파일 손상을 구분하는 Python CLI입니다. 개인 수업 관리 도구에서 파일 동기화 기능을 분리해 공개용으로 재구성했습니다.

같은 주소의 자료가 바뀌면 이전 내용을 보존합니다. 다운로드 이력에 있어도 실제 파일이 없거나 해시가 다르면 다시 받습니다. 계정 없이 실행할 수 있는 가상 자료 데모를 포함합니다.

## 빠르게 실행하기

Python 3.11 이상이 필요합니다. 먼저 저장소를 내려받아 설치합니다. PyPI에 배포한 패키지가 아닙니다.

```sh
git clone https://github.com/jhlee1020lee/course-material-sync.git
cd course-material-sync
python -m venv .venv
```

가상환경을 활성화합니다.

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```sh
# macOS 또는 Linux
source .venv/bin/activate
```

데모에는 외부 패키지나 브라우저가 필요하지 않습니다.

```sh
python -m pip install -e .
course-sync demo --workspace .demo-workspace --json
course-sync demo --workspace .demo-workspace --json
course-sync demo --workspace .demo-workspace --revision 2 --json
```

순서대로 실행하면 처음에는 자료 2개가 추가되고, 두 번째에는 2개 모두 그대로 유지됩니다. 세 번째에는 내용이 바뀐 자료 1개의 새 버전을 저장하고 이전 내용을 보존합니다. 실행 결과의 `items[].path`가 현재 파일 위치를 안내합니다.

계획만 확인하려면 다음 명령을 사용합니다. 데모의 dry-run은 네트워크 요청과 파일 쓰기를 하지 않습니다.

```sh
course-sync demo --workspace .demo-workspace --revision 2 --dry-run --json
```

## 실제 Canvas 연결

이 버전은 Canvas REST API의 Files와 Modules를 사용합니다. Canvas 기반 서비스라도 API 공개 범위와 로그인 정책이 다르면 연결되지 않을 수 있습니다. 비 Canvas LMS의 화면을 자동 탐색하는 기능은 없습니다. 접근 권한이 있는 강좌와 자료에만 사용합니다.

```sh
python -m pip install -e ".[canvas]"
python -m playwright install chromium
```

`examples/config.example.json`을 개인 설정 파일로 복사한 뒤 주소와 강좌 ID를 바꿉니다. 아래 값은 실행 예시이며 실제 강좌가 아닙니다.

```json
{
  "base_url": "https://canvas.example.com",
  "courses": [{"id": 101, "slug": "example-course"}],
  "allowed_download_hosts": [],
  "max_download_mb": 50
}
```

설정 파일을 `config.local.json`으로 저장했다면 다음 순서로 실행합니다.

```sh
course-sync login --config config.local.json --workspace .course-sync
course-sync run --config config.local.json --workspace .course-sync --dry-run --json
course-sync run --config config.local.json --workspace .course-sync --json
```

로그인은 전용 Chromium 창에서 직접 합니다. 로그인이 끝나면 터미널에서 Enter를 누릅니다. 일반 Chrome 프로필을 가져오거나 비밀번호를 설정 파일에 넣지 않습니다. 전용 브라우저 프로필에는 로그인 쿠키 등이 남으므로 작업 폴더를 개인 데이터로 취급합니다.

`run --dry-run`은 파일 목록을 조회하지만 자료 본문 다운로드와 동기화 상태 변경은 하지 않습니다. 브라우저 자체는 전용 프로필을 갱신할 수 있습니다. 로그인 상태가 없거나 만료되면 `login`을 다시 실행합니다. `run --headed`로 전용 브라우저를 표시할 수도 있습니다.

Canvas 파일이 외부 저장소로 이동하는 환경에서는 해당 호스트를 `allowed_download_hosts`에 정확히 추가해야 합니다. 와일드카드나 모든 호스트 허용은 지원하지 않습니다. API 페이지와 다운로드의 리다이렉트를 검사하며, 허용하지 않은 주소로 이동하면 실패로 보고합니다.

## 동작과 결과

```text
Canvas Files / Modules       가상 데모 자료
          |                        |
          +-------- Material ------+
                         |
                 검증 및 동기화
                         |
           현재 파일 + 이전본 + state.json
                         |
                    JSON 실행 결과
```

| 상태 | 의미 |
| --- | --- |
| `added` | 처음 받은 자료 |
| `updated` | 원격 내용이 바뀌어 새 버전을 저장한 자료 |
| `unchanged` | 원격 내용과 저장된 파일의 무결성을 확인한 자료 |
| `repaired` | 로컬 파일 누락 또는 손상을 복구한 자료 |
| `failed` | 가져오기나 저장에 실패한 자료 |
| `planned` | dry-run에서 확인한 후보 |

`--json`은 `schema_version`, `counts`, `items`를 출력합니다. 자료 내용, 쿠키, 서명된 다운로드 URL이나 예외 원문은 결과에 넣지 않습니다. 결과에는 파일명과 강좌별 이름이 있으므로 실제 실행 결과를 공개할 때는 별도로 검토해야 합니다.

현재 파일은 내용 해시가 포함된 이름으로 저장하고 상태 파일을 원자적으로 교체합니다. 개정 전 파일을 덮어쓰지 않으며 원격에서 사라진 자료도 자동 삭제하지 않습니다. 한 파일의 다운로드 실패는 다른 파일 처리와 구분합니다. 잘못된 상태 파일, 위험한 경로와 동시 실행은 작업을 중단합니다.

| 종료 코드 | 의미 |
| --- | --- |
| `0` | 성공 또는 dry-run 완료 |
| `1` | 동기화 실패 또는 일부 파일 실패 |
| `2` | 명령이나 설정 오류 |
| `3` | 로그인 필요 |
| `130` | 사용자 중단 |

## 지원 범위와 한계

- 수집 대상은 Canvas의 파일 항목입니다. 참가자, 점수, 제출물, 토론과 개인 일정은 수집하지 않습니다. 강의계획서도 Canvas 파일로 등록된 경우에 해당합니다.
- 자료가 같은지 확인하려고 실행마다 본문을 가져와 비교합니다. `unchanged`가 네트워크 전송을 생략했다는 뜻은 아닙니다.
- `max_download_mb`는 저장을 허용할 크기입니다. Playwright가 응답을 메모리에 버퍼링하므로 네트워크 전송량이나 최대 메모리 사용량까지 제한하지는 못합니다.
- 인증된 HTML 페이지를 파일로 저장하지 않도록 HTML 응답을 거부합니다. HTML 형식의 강의자료도 이 버전에서는 지원하지 않습니다.
- 원자적 파일 교체를 사용하지만 전원 손실, 파일시스템 고장이나 다른 프로그램의 동시 파일 변경까지 복구를 보장하지 않습니다. 중단 직후에는 상태가 참조하지 않는 파일이 남을 수 있습니다.
- 공개판은 합성 자료와 가상 API 응답으로 검증합니다. 원래 개인 도구의 운영 경험을 공개판의 모든 Canvas 환경 실사용 검증으로 간주하지 않습니다.

## 개발과 검증

```sh
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python scripts/check_public_tree.py
python -m build
python scripts/smoke_install.py
```

테스트는 가상 응답과 임시 폴더를 사용합니다. 실제 학교 계정이나 강의자료가 필요하지 않습니다. CI는 Windows와 Linux에서 테스트, 정적 검사, 배포 파일 빌드와 새 가상환경 설치를 수행합니다.

구조와 실패 처리 설계는 [설계 문서](docs/design.md), 변경 기여 방법은 [기여 안내](CONTRIBUTING.md), 민감정보 취급은 [보안 안내](SECURITY.md)를 참고하세요.

## 제작 배경

수업마다 자료를 다시 확인하면서 같은 파일의 재수집, 개정본 누락, 로컬 파일 손상과 완료 보고의 불일치를 처리할 필요가 있었습니다. 그 과정에서 사용한 동기화 방식을 재사용 가능한 작은 CLI로 정리했습니다.

이 공개판은 AI 코딩 도구를 활용해 구현, 리팩터링, 문서 작성과 검토를 진행했습니다. 테스트와 CI 결과는 확인 범위를 보여 주며, 코드 전체의 무결함을 보증하지 않습니다. 실제 강의자료, 개인 계정, 운영 기록과 기존 비공개 Git 이력은 포함하지 않습니다.

MIT 라이선스로 배포합니다. 라이선스는 이 저장소의 코드와 문서에 적용되며, 사용자가 내려받는 자료의 이용 조건은 각 원자료를 따릅니다.
