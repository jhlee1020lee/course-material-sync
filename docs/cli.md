# 명령과 오류 안내

[처음 설치하고 실행하는 방법](../README.md)을 먼저 읽었다면, 이 문서에서 명령 옵션과 오류별 확인 방법을 찾을 수 있습니다.

## 명령 한눈에 보기

```text
course-sync --version
course-sync demo [--workspace 폴더] [--revision 1|2] [--dry-run] [--json]
course-sync login --config 설정파일 [--workspace 폴더] [--json]
course-sync run --config 설정파일 [--workspace 폴더] [--dry-run] [--headed] [--json]
```

대괄호 `[...]`는 선택 가능한 옵션을 나타내며 실제 명령에 입력하지 않습니다. `course-sync` 대신 `python -m course_material_sync`를 사용해도 됩니다. 두 명령 모두 패키지가 설치된 Python 가상환경에서 실행해야 합니다.

| 명령 | 하는 일 | 실제 계정 필요 |
| --- | --- | --- |
| `demo` | 코드에 포함된 가상 자료 2개로 동기화 동작 확인 | 아니요 |
| `login` | 전용 Chromium에서 직접 로그인하고 설정의 첫 번째 강좌 목록 접근 확인 | 예 |
| `run` | 설정한 모든 강좌의 파일 목록을 모으고 자료 동기화 | 예 |

### 공통 옵션

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| `--workspace` | `.course-sync` | 현재 터미널 위치를 기준으로 한 작업 폴더. 절대 경로도 가능 |
| `--json` | 사용 안 함 | 사람이 읽는 짧은 문장 대신 JSON 결과 출력 |
| `--help` | 해당 없음 | 해당 명령의 사용법 출력 |

경로에 공백이 있으면 따옴표로 감쌉니다.

```sh
course-sync demo --workspace "demo workspace" --json
course-sync run --config "my config.local.json" --workspace "course workspace" --json
```

두 번째 명령은 예시 경로이므로 실제 설정 파일을 먼저 만들어야 합니다. 설정 파일과 작업 폴더의 상대 경로는 모두 **명령을 실행한 터미널의 현재 폴더 기준**입니다.

### 명령별 옵션

| 옵션 | 사용 가능한 명령 | 설명 |
| --- | --- | --- |
| `--revision 1` 또는 `--revision 2` | `demo` | 데모 자료의 개정 번호. 기본값은 1이며, 2는 `lesson-02.txt`에 한 문장을 추가 |
| `--config` | `login`, `run` | 필수 옵션. 개인 Canvas 설정 JSON 파일 |
| `--dry-run` | `demo`, `run` | 후보만 확인하고 파일 본문과 동기화 상태를 저장하지 않음 |
| `--headed` | `run` | 전용 브라우저 창 표시. `login`은 항상 창을 표시 |

`--version`은 `course-sync --version`처럼 최상위 명령에 사용합니다. `--json`, `--workspace`와 다른 옵션은 `demo`, `login`, `run` 뒤에 둡니다. 일부 강좌만 받고 싶으면 `courses`에 그 강좌들만 넣은 별도 설정 파일을 사용하세요. 현재 `--course` 선택 옵션은 없습니다.

## dry-run에서 실제로 하는 일

| 동작 | `demo --dry-run` | `run --dry-run` |
| --- | --- | --- |
| 로그인 확인과 원격 API 조회 | 없음 | 있음 |
| 자료 본문 가져오기 | 없음 | 없음 |
| 현재 자료 파일 쓰기 | 없음 | 없음 |
| `state.json` 쓰기 | 없음 | 없음 |
| 브라우저 프로필 변경 가능성 | 없음 | 있음 |

두 명령 모두 기존 상태 파일이 있다면 구조를 검증합니다. 잘못된 상태 파일은 dry-run에서도 오류가 납니다. `planned`는 후보를 세는 상태이며, 아직 본문을 비교하지 않았으므로 추가와 변경 개수를 예측하지 않습니다.

## 실행 결과 읽기

파일 동기화가 끝나면 `schema_version`, `counts`, `items`가 있는 결과를 출력합니다. 다음은 파일명과 상태만 보는 일반 출력입니다.

```text
added=0 updated=1 unchanged=1 repaired=0 failed=0 planned=0
unchanged: demo-course/lesson-01.txt
updated: demo-course/lesson-02.txt
```

JSON이 필요하면 `--json`을 붙입니다. 각 항목에는 `course`, `id`, `filename`, `status`가 있고, 저장한 현재본에는 작업 폴더 기준 `path`, 실패에는 `error_code`가 추가됩니다.

| 상태 | 의미 |
| --- | --- |
| `added` | 해당 강좌와 자료 ID를 처음 저장 |
| `updated` | 같은 자료 ID의 내용 또는 파일명이 바뀜 |
| `unchanged` | 가져온 내용과 로컬 현재본의 해시가 모두 일치 |
| `repaired` | 원격 내용은 같지만 로컬 현재본이 없거나 달라 복구 |
| `failed` | 해당 항목을 처리하지 못함 |
| `planned` | dry-run에서 처리 후보로 확인 |

이전본은 기존 로컬 현재본의 해시가 저장 기록과 일치할 때 보관합니다. 원격 개정이 생겼는데 이전 로컬 현재본이 없거나 수정돼 있으면 `updated` 항목에 `previous_local_copy: "unavailable_or_modified"`가 추가됩니다. 이때 확보하지 못한 이전 내용을 원격에서 복원해 이력에 넣지는 않습니다.

전체 명령이 실패하면 `counts`와 `items` 없이 `error_code`만 나올 수 있습니다. 인증이 개별 다운로드 도중 만료된 경우에는 부분 결과와 `error_code: "authentication_required"`가 함께 나올 수 있습니다. `counts.failed`뿐 아니라 최상위 `error_code`와 종료 코드도 확인하세요.

결과는 표준 출력으로 나가며 자동으로 로그 파일을 만들지 않습니다. 다음처럼 저장할 수 있지만, 결과의 강좌 이름과 파일명도 개인 실행 데이터일 수 있습니다.

```sh
course-sync run --config config.local.json --workspace .course-sync --json > result.local.json
```

`login`의 대화형 안내는 표준 오류로 출력되며 터미널에서 직접 Enter를 눌러야 합니다. 로그인 명령을 입력을 받을 수 없는 환경에서 실행하면 `interactive_login_required` 오류가 납니다.

### 종료 코드

| 코드 | 의미 | 다음 행동 |
| --- | --- | --- |
| `0` | 명령 또는 dry-run 완료 | 결과와 현재본 경로 확인 |
| `1` | 일부 파일 실패 또는 일반 실행 실패 | 오류 코드와 실패 항목 확인 |
| `2` | 명령 또는 설정 오류 | 옵션과 설정 파일 수정 |
| `3` | 로그인 또는 접근 권한 확인 필요 | 전용 브라우저에서 재인증하고 해당 강좌 접근 확인 |
| `130` | 사용자가 중단 | 다른 실행이 없는지 확인하고 같은 설정으로 재실행 |

명령 직후 PowerShell에서는 `$LASTEXITCODE`, macOS와 Linux에서는 `echo $?`로 종료 코드를 확인할 수 있습니다. 명령행 문법 오류는 `--json`을 사용해도 argparse의 일반 도움말로 출력될 수 있습니다.

## 설정 파일 문제

| 오류 코드 | 확인할 것 |
| --- | --- |
| `config_unreadable` | 파일 경로와 읽기 권한, UTF-8 JSON 문법. 주석과 마지막 쉼표 제거 |
| `config_too_large` | 설정 파일 크기 제한은 1MiB. 강의자료나 다른 내용을 설정 파일에 넣지 않았는지 확인 |
| `base_url_required` | `base_url`이 문자열인지 확인 |
| `base_url_must_be_https_origin`, `invalid_base_url` | `https://호스트` 형태 사용. 사용자 정보, 강좌 경로, 쿼리, 조각 식별자와 443 이외 포트 제외 |
| `courses_required` | `courses`에 강좌를 하나 이상 지정 |
| `invalid_course_id` | 강좌 URL에 쓰이는 양의 정수를 입력. 문자열 `"101"`과 숫자 `101`을 구분 |
| `invalid_course_slug` | 소문자로 시작하는 영문 소문자, 숫자, `_`, `-` 조합 사용. 최대 48자. `con`, `nul` 같은 Windows 예약명 제외 |
| `duplicate_course` | 강좌 ID와 `slug`가 각각 중복되지 않는지 확인 |
| `invalid_course_fields`, `config_unknown_fields` | 예제에 정의되지 않은 항목을 넣지 않았는지 확인 |
| `invalid_download_hosts`, `invalid_download_host` | 호스트 이름만 사용. 소문자로 적고 `https://`, 경로, 포트, `*` 제외 |
| `invalid_download_limit` | `max_download_mb`를 1~1024의 정수로 입력 |

## 로그인과 다운로드 문제

| 오류 또는 상황 | 확인 방법 |
| --- | --- |
| `login_required` | 같은 `--workspace`로 `login`을 실행했는지 확인. 작업 폴더를 바꾸면 로그인 프로필도 달라짐 |
| `authentication_required` | 로그인 만료뿐 아니라 강좌나 파일의 접근 권한 부족도 가능. 브라우저에서 해당 강좌와 파일을 직접 확인 |
| `authentication_redirect`, `authentication_html` | API나 파일 요청에 로그인 화면 또는 HTML이 돌아온 경우. 재인증하고 기관 정책 확인. 실제 HTML 자료는 지원 대상이 아님 |
| `install_canvas_extra_and_chromium` | Canvas 선택 의존성과 Chromium 설치 후 다시 실행 |
| `untrusted_download_origin` | 외부 다운로드 호스트를 실제로 확인한 뒤 `allowed_download_hosts`에 추가 |
| `FETCH_FAILED` | 개별 파일 가져오기 실패를 모은 코드. 브라우저에서 다운로드 가능한지, 인증이 유지되는지, 외부 호스트와 크기 제한이 맞는지 확인 |
| `request_failed`, `http_error` | 목록 조회의 네트워크, HTTP 상태 또는 학교 서비스 상태 확인. 일반 브라우저에서 파일 목록에 접근되는지 확인 |
| `unexpected_metadata_type`, `invalid_metadata_json`, `incomplete_module_items` | 기대한 Canvas API 형식이나 완전한 목록을 얻지 못함. 일부 화면에 접속된다는 이유만으로 전체 수집 완료로 판단하지 않음 |
| `pagination_cycle`, `pagination_limit` | 목록의 다음 페이지가 반복되거나 페이지 한도에 도달. 현재 API 목록당 최대 100페이지이며 명령행에서 변경하는 옵션은 없음 |
| 결과의 후보 수가 `0` | 강좌 ID, 권한, 파일 게시 여부, 지원 형식을 확인. 숨김, 잠금, 미게시 자료와 지원하지 않는 형식은 대상에서 제외 |
| `operation_failed` | 개인정보가 섞일 수 있는 세부 예외를 숨긴 일반 오류. Chromium 설치와 실행 가능 여부, 작업 폴더 쓰기 권한을 확인 |

다운로드 단계의 비인증 Canvas 오류는 `FETCH_FAILED`로 표시될 수 있으므로, 크기 초과나 호스트 차단의 세부 코드가 항상 사용자에게 출력되지는 않습니다. 실제 계정이나 인증 URL을 이슈에 올려 진단하려 하지 말고, 먼저 가상 데이터로 재현할 수 있는지 확인하세요.

## 작업 폴더와 상태 파일 문제

| 오류 코드 | 의미와 처리 방법 |
| --- | --- |
| `WORKSPACE_BUSY` | 같은 폴더의 동기화 실행이 이미 잠금을 가지고 있거나, 중단 후 `.sync.lock`이 남음 |
| `INVALID_STATE` | `state.json` 형식이나 기록이 유효하지 않음. 파일을 빈 상태로 덮어쓰거나 임의 수정하지 말고 기존 폴더를 보존 |
| `UNSAFE_WORKSPACE`, `workspace_link_not_allowed` | 경로에 심볼릭 링크, Windows junction 또는 예상하지 않은 파일 유형이 있음. 일반 로컬 폴더 사용 |
| `invalid_workspace` | 드라이브 루트나 폴더가 아닌 경로를 작업 폴더로 지정 |
| `UNSAFE_NAME` | 파일명에 경로 구분자, 제어문자, 예약명 등이 있거나 허용 길이를 넘음. 현재 코어의 파일명 제한은 120자 |
| `SIZE_LIMIT` | 동기화 코어가 받은 본문이 크기 제한을 넘음. Canvas 단계에서 먼저 차단되면 `FETCH_FAILED`일 수 있음 |
| `STATE_WRITE_FAILED`, `STORAGE_FAILED`, `WORKSPACE_IO_FAILED` | 디스크 여유 공간과 읽기 또는 쓰기 권한 확인. 기존 폴더를 보존한 채 원인을 해결한 뒤 재실행 |
| `TARGET_CONFLICT`, `HISTORY_CONFLICT` | 저장하려는 위치에 예상과 다른 내용이 존재. 기존 자료를 확인하고 보존한 뒤 처리 |
| `LOCAL_CHANGED_DURING_SYNC` | 처리 중 다른 프로그램이 로컬 파일을 바꿈. 해당 편집을 중단한 뒤 재실행 |
| `STATE_SIZE_LIMIT` | 동기화 상태가 8MiB 한도를 넘음. 현재판에는 이력 압축이나 자동 정리 명령이 없음 |

잠금이 남았다면 먼저 같은 폴더를 사용하는 `course-sync` 실행이 모두 종료됐는지 확인합니다. 종료를 확인한 뒤에만 해당 작업 폴더의 `.sync.lock`을 제거하고 재실행합니다. 실행 중인지 판단할 수 없다면 잠금을 지우지 마세요. 도구는 남은 잠금을 자동으로 무효화하지 않습니다.

상태 파일 복구가 어렵다면 기존 작업 폴더 전체를 보존하고 **새 폴더 이름**으로 다시 로그인하고 수집할 수 있습니다. 새 폴더에서는 이전 이력을 알 수 없으므로 자료를 처음 받은 것으로 처리합니다. 새 수집을 마쳤다고 기존 폴더와 이력이 복구된 것은 아닙니다.

## 지원하는 파일 형식

확장자는 대소문자를 구분하지 않습니다. 현재 코드에 등록된 목록은 다음과 같습니다.

| 종류 | 확장자 |
| --- | --- |
| 문서와 프레젠테이션 | `.pdf`, `.ppt`, `.pptx`, `.doc`, `.docx`, `.hwp`, `.hwpx`, `.odt`, `.odp` |
| 표와 데이터 | `.xls`, `.xlsx`, `.ods`, `.csv`, `.json` |
| 일반 텍스트 | `.txt`, `.md` |
| 압축 파일 | `.zip`, `.tar`, `.gz`, `.7z` |
| 노트북과 코드 | `.ipynb`, `.py`, `.c`, `.h`, `.cpp`, `.hpp`, `.java`, `.scala`, `.rs`, `.r`, `.m`, `.sql` |
| 이미지 | `.png`, `.jpg`, `.jpeg`, `.svg` |

HTML, 영상, 음성과 목록 밖의 확장자는 제외됩니다. 문서 내용을 추출하거나 압축을 해제하지 않고 받은 바이트를 저장합니다. 지원 확장자라도 잠금, 숨김, 미게시 또는 업로드 미완료 항목은 제외할 수 있습니다.

내려받은 파일에 개인정보가 있는지, 저작권상 공유할 수 있는지는 자동 판정하지 않습니다. [보안 안내](../SECURITY.md)와 [동기화 설계](design.md)에서 저장 범위와 실패 처리 한계를 확인할 수 있습니다.
