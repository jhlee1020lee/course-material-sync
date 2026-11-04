# course-material-sync

[![CI](https://github.com/jhlee1020lee/course-material-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/jhlee1020lee/course-material-sync/actions/workflows/ci.yml)

**Canvas LMS에 올라온 강의 파일을 컴퓨터에 모으고, 개정본과 이전본을 함께 관리하는 명령행 도구입니다.**

강의자료를 받았는데 교수가 같은 파일을 수정했거나, 내려받았던 파일을 실수로 지웠을 때 쓸 수 있습니다. 실행할 때 원격 자료와 저장된 파일의 내용을 비교해 새 자료, 개정 자료, 그대로인 자료, 복구한 자료를 구분합니다. 파일 내용을 읽어 요약하거나 교재를 만드는 기능은 포함하지 않습니다.

처음에는 학교 계정을 연결하지 않아도 됩니다. 아래 데모에서 가상 강의자료 2개를 받아 보고, 두 번째 실행과 개정본 처리 결과까지 확인할 수 있습니다.

- [1. 설치](#1-설치)
- [2. 계정 없이 동작 확인하기](#2-계정-없이-동작-확인하기)
- [3. 실제 Canvas 강좌 연결하기](#3-실제-canvas-강좌-연결하기)
- [4. 다운로드한 파일 찾기](#4-다운로드한-파일-찾기)
- [문제가 생겼을 때](#문제가-생겼을-때)
- [전체 명령과 오류 코드](docs/cli.md)

## 어떤 일을 해 주나요?

| 상황 | 실행 결과 |
| --- | --- |
| 처음 보는 파일이 올라옴 | 새 파일을 저장하고 `added`로 표시 |
| 같은 자료의 내용이나 파일명이 바뀜 | 새 버전을 저장하고, 기존 로컬 현재본이 정상이라면 이전본으로 보관한 뒤 `updated`로 표시 |
| 원격 내용과 로컬 파일이 모두 그대로임 | `unchanged`로 표시 |
| 원격은 그대로인데 로컬 현재본을 지웠거나 내용을 바꿈 | 원격 내용으로 복구하고 `repaired`로 표시 |
| 한 파일을 가져오지 못함 | 그 파일을 `failed`로 기록하고 다른 파일 처리 계속 |

각 자료는 Canvas 파일 ID와 설정한 강좌 이름으로 구분합니다. 이름이 같은 다른 자료도 별도 파일로 저장합니다. 원격 파일을 수정하거나 삭제하지 않으며, 원격 목록에서 사라진 자료도 로컬에서 자동 삭제하지 않습니다.

이미 지웠거나 수정한 이전 로컬 현재본을 원격에서 되찾아 보관하는 기능은 없습니다. 원격 개정과 함께 이런 상태를 발견하면 JSON 항목에 `previous_local_copy: "unavailable_or_modified"`를 표시합니다. 이전본 보존은 기존 로컬 현재본의 내용이 저장 기록과 일치할 때 가능합니다.

현재 버전은 **Canvas의 Files와 Modules API에 접근할 수 있는 환경**을 대상으로 합니다. 모든 대학 LMS에 공통으로 연결되는 프로그램은 아닙니다. Canvas를 사용하더라도 학교의 로그인 정책과 API 권한에 따라 연결되지 않을 수 있습니다.

## 1. 설치

### 먼저 준비할 것

| 항목 | 데모 | 실제 강좌 연결 |
| --- | --- | --- |
| Python 3.11 이상 | 필요 | 필요 |
| 저장소 코드 | 필요 | 필요 |
| 학교 또는 기관의 Canvas 계정 | 불필요 | 필요 |
| Playwright와 전용 Chromium 브라우저 | 불필요 | 추가 설치 |
| 인터넷 | 코드와 설치 도구를 받을 때 사용 | 로그인과 자료 조회에 사용 |

Python이 없다면 [Python 공식 다운로드](https://www.python.org/downloads/)에서 설치합니다. 저장소를 명령으로 내려받으려면 [Git](https://git-scm.com/downloads/)도 필요합니다. Git을 쓰지 않는다면 이 페이지의 **Code → Download ZIP**으로 내려받아 압축을 풀어도 됩니다.

이 프로젝트는 아직 PyPI에 배포하지 않았습니다. **저장소를 내려받은 뒤 그 폴더에서 설치**해야 합니다. 아래 명령은 운영체제에 맞는 한 묶음만 실행하세요.

### Windows PowerShell

PowerShell을 열고 다음 명령을 한 줄씩 실행합니다. 첫 명령에서 Python 버전이 3.11 이상인지 확인하세요.

```powershell
py -3 --version
git clone https://github.com/jhlee1020lee/course-material-sync.git
cd course-material-sync
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
course-sync --version
```

`py`를 찾을 수 없지만 `python --version`은 3.11 이상을 출력한다면, 위의 `py -3` 두 곳을 `python`으로 바꾸면 됩니다. ZIP으로 받았다면 `git clone`을 건너뛰고 압축을 푼 폴더로 이동한 뒤 가상환경을 만드세요. 그 폴더 안에 `pyproject.toml`이 있어야 합니다.

**`Activate.ps1` 실행이 차단되면** 실행 정책을 바꾸지 않고 가상환경의 실행 파일을 직접 사용할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\course-sync.exe --version
.\.venv\Scripts\course-sync.exe --help
```

이 방식을 선택했다면 아래의 `python`은 `.\.venv\Scripts\python.exe`로, `course-sync`는 `.\.venv\Scripts\course-sync.exe`로 바꿔 실행합니다.

### macOS 또는 Linux

터미널에서 다음 명령을 실행합니다. `python3 --version`이 3.11 이상이어야 합니다.

```sh
python3 --version
git clone https://github.com/jhlee1020lee/course-material-sync.git
cd course-material-sync
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
course-sync --version
```

ZIP으로 받았다면 `git clone` 대신 압축을 푼 폴더로 이동합니다. Linux에서 `venv`나 `ensurepip`가 없다는 오류가 나면 배포판에서 제공하는 해당 Python 버전의 가상환경 패키지를 먼저 설치하세요.

### 설치가 끝났는지 확인

`course-sync --version`에서 설치된 버전 번호가 나오면 명령을 사용할 수 있습니다. `.venv`는 이 프로젝트에 필요한 Python 환경을 담는 폴더입니다. 새 터미널을 열 때는 프로젝트 폴더로 이동한 뒤 활성화 명령을 다시 실행하거나 가상환경의 실행 파일을 직접 사용하세요. [Python 가상환경 설명](https://docs.python.org/3/library/venv.html)

아래 예제는 모두 **저장소의 최상위 폴더에서 실행**한다고 가정합니다. `--workspace`는 다운로드 결과와 실행 상태를 넣을 폴더이며, 데모와 실제 수업은 서로 다른 폴더를 사용합니다.

## 2. 계정 없이 동작 확인하기

데모는 코드에 포함된 가상 텍스트 자료를 사용합니다. 설치 후 데모 실행에는 계정, 브라우저, 네트워크가 필요하지 않습니다. 출력에 등장하는 `demo-course`는 실제 강좌가 아닙니다.

아래 3개 명령은 **같은 `.demo-workspace`를 사용해 순서대로** 실행하세요. 해당 폴더를 이미 사용했다면 `.demo-workspace-2`처럼 새 이름을 세 명령에 똑같이 지정하면 처음부터 확인할 수 있습니다.

### 첫 번째 실행: 새 자료 2개 저장

```sh
course-sync demo --workspace .demo-workspace
```

```text
added=2 updated=0 unchanged=0 repaired=0 failed=0 planned=0
added: demo-course/lesson-01.txt
added: demo-course/lesson-02.txt
```

`.demo-workspace/files/demo-course/` 안에 가상 강의자료 2개가 생깁니다. 실제 저장 파일명에는 서로 다른 자료와 개정본을 구별하는 해시가 붙습니다.

### 두 번째 실행: 바뀌지 않은 자료 확인

```sh
course-sync demo --workspace .demo-workspace
```

```text
added=0 updated=0 unchanged=2 repaired=0 failed=0 planned=0
unchanged: demo-course/lesson-01.txt
unchanged: demo-course/lesson-02.txt
```

같은 자료를 다시 받더라도 현재 내용이 같으면 새 개정본을 만들지 않습니다.

### 세 번째 실행: 개정본 1개 반영

```sh
course-sync demo --workspace .demo-workspace --revision 2
```

```text
added=0 updated=1 unchanged=1 repaired=0 failed=0 planned=0
unchanged: demo-course/lesson-01.txt
updated: demo-course/lesson-02.txt
```

두 번째 자료의 현재본에는 다음 문장이 추가됩니다.

```text
Revision 2: the empty set.
```

변경 전 내용은 `.demo-workspace/history/`에 남습니다. 이후 개정본 상태를 다시 확인할 때도 `--revision 2`를 붙이세요. 옵션을 빼면 데모의 기본값인 1번 개정을 다시 가져옵니다.

### 저장하지 않고 대상만 확인

```sh
course-sync demo --workspace .demo-workspace --revision 2 --dry-run --json
```

`counts.planned`가 `2`이고 나머지 개수는 `0`입니다. 이때는 자료를 가져오거나 파일과 상태를 쓰지 않습니다. `planned`는 처리할 후보 수이며, 실제로 몇 개가 개정됐는지를 확인한 수치는 아닙니다.

## 3. 실제 Canvas 강좌 연결하기

### 3-1. 연결에 필요한 패키지와 브라우저 설치

가상환경을 활성화한 상태에서 실행합니다.

```sh
python -m pip install -e ".[canvas]"
python -m playwright install chromium
```

두 번째 명령은 이 도구가 사용하는 Chromium을 설치합니다. 평소 사용하는 Chrome의 로그인 정보를 가져오지 않습니다.

### 3-2. 내 강좌 설정 파일 만들기

예제 파일을 복사합니다.

```powershell
# Windows PowerShell
Copy-Item -LiteralPath examples/config.example.json -Destination config.local.json
```

```sh
# macOS 또는 Linux
cp examples/config.example.json config.local.json
```

`config.local.json`을 텍스트 편집기로 열고 아래 항목을 자신의 환경에 맞게 바꿉니다. 이 예시는 가상의 주소와 강좌입니다.

```json
{
  "base_url": "https://canvas.example.com",
  "courses": [
    {"id": 101, "slug": "programming"},
    {"id": 102, "slug": "discrete-math"}
  ],
  "allowed_download_hosts": [],
  "max_download_mb": 50
}
```

| 항목 | 무엇을 넣나요? |
| --- | --- |
| `base_url` | 로그인 후 사용하는 Canvas의 HTTPS 기본 주소. `/courses/101` 같은 경로는 제외 |
| `courses[].id` | 강좌 페이지 주소의 `/courses/` 다음 숫자. 학교의 교과목 코드나 학번이 아님 |
| `courses[].slug` | 이 컴퓨터에서 강좌를 구별할 이름. 소문자로 시작하고 영문 소문자, 숫자, `_`, `-`만 사용. 최대 48자 |
| `allowed_download_hosts` | Canvas 기본 주소 밖에 있는 파일 서버의 호스트 이름. 처음에는 빈 배열로 두고 필요한 경우에만 지정 |
| `max_download_mb` | 파일 하나의 저장 허용 크기. 기본값 50, 정수 1~1024. 프로그램은 1MB를 1,048,576바이트로 계산 |

예를 들어 강좌 주소가 `https://canvas.example.com/courses/101/modules`라면 기본 주소는 `https://canvas.example.com`, 강좌 ID는 `101`입니다. 자신의 강좌가 하나면 `courses`에 항목 하나만 남깁니다. 여러 강좌의 ID와 `slug`는 각각 중복되지 않아야 합니다.

처음 설정할 때 정한 `slug`와 작업 폴더는 계속 같은 값을 쓰세요. 도구가 강좌와 이전 다운로드 이력을 연결할 때 사용합니다. 설정 파일에는 비밀번호, 인증 코드나 API 토큰을 넣지 않습니다. JSON에는 주석을 쓰거나 마지막 항목 뒤에 쉼표를 붙일 수 없습니다.

### 3-3. 전용 브라우저에서 직접 로그인

```sh
course-sync login --config config.local.json --workspace .course-sync
```

1. 새 Chromium 창이 열리면 학교 또는 기관의 계정으로 로그인합니다.
2. 추가 인증이 있다면 브라우저에서 직접 완료합니다.
3. 설정한 첫 번째 강좌에 들어갈 수 있는지 확인합니다.
4. 터미널로 돌아와 Enter를 누릅니다. 비밀번호나 인증 코드를 터미널에 입력하지 않습니다.

첫 번째 강좌의 파일 목록을 조회할 수 있으면 `login_verified`가 나옵니다. 이는 해당 계정의 모든 강좌와 파일 다운로드를 검증했다는 뜻은 아닙니다. 다음 단계에서 설정한 강좌 전체를 확인합니다.

브라우저 프로필은 `.course-sync/.browser-profile/`에 저장됩니다. 같은 작업 폴더를 지정해야 이후 실행에서 이 로그인을 재사용할 수 있습니다.

### 3-4. 내려받을 목록부터 확인

```sh
course-sync run --config config.local.json --workspace .course-sync --dry-run --json
```

`items`의 강좌와 파일명이 예상한 자료인지 확인합니다. 이 명령은 실제 Canvas 목록을 조회하므로 **네트워크와 로그인 상태가 필요**합니다. 파일 본문 다운로드와 `state.json` 갱신은 하지 않지만, Chromium이 로그인 프로필을 갱신할 수 있습니다. 앞의 데모 dry-run과 다른 점입니다.

후보가 `0`이면 강좌 ID, 접근 권한, 지원 파일 형식을 확인하세요. 해당 수업에 자료가 전혀 없다고 단정할 수는 없습니다.

### 3-5. 실제 파일 저장

```sh
course-sync run --config config.local.json --workspace .course-sync --json
```

첫 실행에는 주로 `added`, 이후에는 자료 상태에 따라 `updated`, `unchanged`, `repaired`가 나옵니다. `counts.failed`가 `0`인지 확인하고, 실패한 항목이 있으면 `items[].error_code`를 봅니다. 정상적으로 저장한 다른 파일은 유지됩니다.

다음에 새 자료를 확인할 때도 **같은 명령, 같은 설정, 같은 작업 폴더**를 사용합니다. 프로그램은 명령을 실행할 때 동작하며 정기 실행을 자동 등록하지 않습니다. 로그인 만료나 추가 인증으로 실패하면 3-3의 `login`을 다시 실행합니다. 실행 중 브라우저를 보고 싶다면 `run`에 `--headed`를 붙이세요.

## 4. 다운로드한 파일 찾기

`--workspace .course-sync`로 실행했다면 저장 위치는 다음과 같습니다. 데모를 실행했다면 맨 위 이름만 `.demo-workspace`로 바뀝니다.

```text
.course-sync/
├── files/                 현재 파일
│   └── programming/       설정에서 지정한 slug
├── history/               개정 전 파일
├── state.json             현재본 경로, 해시와 이전본 목록
└── .browser-profile/      실제 Canvas 로그인 프로필
```

`history/`는 정상적인 기존 현재본을 이전본으로 보관할 때 생성됩니다. 이미 없거나 변경된 이전 내용은 복원해서 채우지 않습니다. `.browser-profile/`은 실제 Canvas 연결에서 사용하며 데모에는 없습니다. 실행 중에는 중복 실행을 막는 `.sync.lock`도 잠시 만들어집니다.

파일명 뒤쪽에는 `lecture.pdf` 같은 원래 이름이 남습니다. 앞쪽의 긴 문자열은 자료 ID와 내용 해시이며 파일 충돌과 버전 혼동을 막는 데 사용합니다. 파일명을 직접 바꾸면 다음 실행에서 현재본이 없다고 판단할 수 있으므로, 읽거나 편집할 사본은 다른 폴더에 복사해 사용하세요.

### JSON 결과에서 정확한 현재본 경로 확인

`--json`을 붙이면 프로그램이 읽기 쉬운 JSON 한 개를 출력합니다. 일반 출력과 달리 각 파일의 저장 경로도 포함합니다.

| 출력 항목 | 읽는 방법 |
| --- | --- |
| `schema_version` | 결과 형식의 버전 |
| `counts` | 상태별 자료 수 |
| `items[].filename` | 원래 파일명 |
| `items[].status` | `added`, `updated` 등의 처리 결과 |
| `items[].path` | 작업 폴더 안에서 현재 파일까지의 상대 경로. 실패나 dry-run 항목에는 없을 수 있음 |
| `items[].error_code` | 항목 처리 실패의 원인을 나타내는 코드 |

예를 들어 `path`가 `files/programming/...-lecture.pdf`라면 실제 위치는 `.course-sync/files/programming/...-lecture.pdf`입니다. 여기의 `...`는 설명을 위해 줄인 부분이며, 실제 JSON에는 전체 파일명이 나옵니다.

PowerShell에서는 다음처럼 데모 결과의 파일명과 경로만 표로 볼 수 있습니다.

```powershell
$result = course-sync demo --workspace .demo-workspace --revision 2 --json | ConvertFrom-Json
$result.items | Select-Object filename, status, path
```

이전 실행의 현재본과 개정 이력을 찾으려면 `state.json`의 `materials` 안에서 해당 `filename`을 찾습니다. 그 항목의 `path`가 현재본이고 `history` 배열의 `path`가 이전본입니다. 상태 파일은 프로그램이 관리하므로 직접 편집하지 마세요. JSON 실행 결과 자체는 화면에 출력되며 자동으로 별도 보고서 파일에 저장되지는 않습니다.

## 문제가 생겼을 때

| 보이는 상황 | 먼저 확인할 것 |
| --- | --- |
| `course-sync` 명령을 찾지 못함 | 저장소 폴더에서 가상환경을 활성화했는지 확인. `python -m course_material_sync --help`로도 실행 가능 |
| `No module named course_material_sync` | 현재 Python에 설치되지 않은 상태. 가상환경을 선택한 뒤 `python -m pip install -e .` 실행 |
| `Activate.ps1` 실행 차단 | 위 Windows 안내처럼 `.venv` 안의 실행 파일을 직접 사용 |
| `install_canvas_extra_and_chromium` | `python -m pip install -e ".[canvas]"`와 `python -m playwright install chromium` 실행 |
| `config_unreadable` 또는 `invalid_course_id` | 설정 경로, JSON 문법, 강좌 주소의 숫자 확인 |
| `login_required`, `authentication_required`, `authentication_redirect`, `authentication_html` | 같은 작업 폴더로 다시 로그인. 계속되면 설정한 강좌 접근 권한과 로그인 정책 확인 |
| `untrusted_download_origin` | 학교가 쓰는 외부 파일 서버인지 확인한 뒤 정확한 호스트를 설정에 추가. 아래 설명 참고 |
| 항목에 `FETCH_FAILED`가 있음 | 개별 다운로드가 실패했다는 뜻. 로그인, 외부 파일 서버, 크기 제한과 해당 파일의 브라우저 다운로드 여부를 차례로 확인 |
| `WORKSPACE_BUSY` | 같은 작업 폴더를 사용하는 실행이 끝날 때까지 기다림. 중단 후 남은 잠금은 [상세 해결 절차](docs/cli.md#작업-폴더와-상태-파일-문제) 참고 |
| `INVALID_STATE` | 기존 작업 폴더를 보존하고 원인 확인. 상태 파일을 빈 파일로 덮어쓰지 않음 |
| `UNSAFE_WORKSPACE`, `workspace_link_not_allowed` | 심볼릭 링크나 Windows junction을 거치지 않는 일반 폴더로 작업 위치 지정 |
| `operation_failed` | 세부 예외를 숨긴 일반 오류. Playwright와 Chromium 설치, 폴더 권한을 확인하고 `run --headed`로 브라우저 상태 확인 |

개별 다운로드의 비인증 오류는 현재 `FETCH_FAILED`로 묶일 수 있습니다. 오류 코드만으로 크기 초과인지 외부 호스트 차단인지 단정할 수 없습니다. [전체 명령과 오류 설명](docs/cli.md)에서 확인 순서를 볼 수 있습니다.

### 외부 파일 서버를 사용하는 경우

Canvas 주소가 `canvas.example.com`인데 파일을 받을 때 `files.example.com`으로 이동한다면, 해당 호스트를 확인한 뒤 다음처럼 설정합니다.

```json
"allowed_download_hosts": ["files.example.com"]
```

여기에는 `https://`, 파일 경로, 쿼리 문자열을 넣지 않습니다. 소문자 호스트 이름만 사용하며, 와일드카드나 모든 호스트 허용은 지원하지 않습니다. 실제 다운로드가 거치는 외부 호스트를 각각 확인해야 합니다. 브라우저에서 해당 파일을 직접 열어 확인할 수 있지만, 인증 정보가 포함된 전체 다운로드 주소를 공개 이슈에 붙여 넣지는 마세요.

## 지원 범위와 개인정보

- PDF, PowerPoint, Word, 한글 문서, 텍스트, 일부 코드와 압축 파일 등 등록된 확장자를 수집합니다. [지원 형식 전체](docs/cli.md#지원하는-파일-형식)를 확인하세요. HTML 문서, 영상, 음성과 지원 목록 밖의 형식은 수집 대상에서 제외됩니다.
- 파일 항목과 모듈의 파일 연결을 읽습니다. 참가자 명단, 성적, 제출물, 토론, 퀴즈 문항이나 개인 일정을 조회하는 기능은 없습니다. 강의계획서도 파일로 등록돼 있어야 수집할 수 있습니다.
- **파일을 자동으로 익명화하지 않습니다.** 접근 가능한 PDF나 문서 자체에 이름, 이메일과 다른 개인정보가 들어 있다면 그 내용도 내려받습니다. 받은 자료를 공개해도 되는지는 별도로 확인해야 합니다.
- 애플리케이션이 만드는 `state.json`과 JSON 실행 결과에는 다운로드 URL, 쿠키, 응답 본문과 예외 원문을 넣지 않습니다. 강좌의 `slug`, 파일명, 자료 ID와 경로는 포함하므로 실행 결과도 공개 전에 확인해야 합니다.
- 로그인 프로필에는 쿠키와 웹 저장소 등이 남습니다. `config.local.json`, 작업 폴더, 다운로드 자료와 브라우저 프로필은 개인 실행 데이터로 취급하세요. `.gitignore`가 이미 추적 중이거나 강제로 추가한 파일까지 보호하지는 않습니다.
- 현재 내용 확인을 위해 실행마다 원격 파일 본문을 다시 가져옵니다. `unchanged`도 네트워크 전송을 생략했다는 뜻은 아닙니다.
- `max_download_mb`는 저장 허용 크기입니다. Playwright가 응답을 메모리에 버퍼링하므로 전송량과 최대 메모리 사용량의 상한을 보장하지는 않습니다.
- 잘못된 상태 파일과 위험한 경로는 조용히 초기화하지 않고 중단합니다. 전원 손실, 파일시스템 고장, 다른 프로그램의 동시 파일 변경까지 완전히 복구하는 도구는 아닙니다. 중단 시 상태가 참조하지 않는 파일이 남을 수 있습니다.

접근 권한이 있는 강좌와 자료에만 사용하세요. 공개판은 가상 자료와 API 응답으로 검증했으며, 모든 Canvas 환경에서의 실제 계정 연결을 확인한 제품은 아닙니다. 민감정보 취급과 문제 신고는 [보안 안내](SECURITY.md)를 따릅니다.

## 개발과 검증

설치한 가상환경에서 다음 명령으로 테스트와 검사를 실행할 수 있습니다.

```sh
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python scripts/check_public_tree.py
python -m build
python scripts/smoke_install.py
```

테스트는 가상 응답과 임시 폴더를 사용합니다. 실제 학교 계정이나 강의자료가 필요하지 않습니다. CI는 Windows와 Linux의 Python 3.11, 3.14에서 테스트, 정적 검사, 배포 파일 빌드와 새 가상환경 설치를 실행하도록 구성돼 있습니다. macOS 설치 방법을 제공하지만 현재 CI 실행 환경에는 macOS가 포함되지 않습니다. 위의 CI 배지에서 현재 실행 결과를 확인할 수 있습니다.

코드 구조와 실패 처리 방식은 [설계 문서](docs/design.md), 변경을 제안하는 방법은 [기여 안내](CONTRIBUTING.md)를 참고하세요.

## 제작 배경과 라이선스

수업마다 자료를 다시 확인하면서 개정본 누락, 로컬 파일 손상과 완료 보고의 불일치를 처리할 필요가 있었습니다. 개인 수업 관리 도구에서 사용하던 동기화 방식을 작은 CLI로 분리하고, 계정 없이 검증할 수 있는 데모와 테스트를 붙였습니다.

AI 코딩 도구를 활용해 구현, 리팩터링, 문서 작성과 검토를 진행했습니다. 원래 개인 도구의 운영 경험과 공개판의 검증 범위는 구분합니다. 실제 강의자료, 개인 계정, 운영 기록과 기존 비공개 Git 이력은 이 저장소에 포함하지 않습니다.

[MIT 라이선스](LICENSE)는 이 저장소의 코드와 문서에 적용됩니다. 사용자가 내려받는 자료의 이용 조건은 각 원자료를 따릅니다.
