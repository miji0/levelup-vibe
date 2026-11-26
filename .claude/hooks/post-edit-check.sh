#!/bin/bash
# PostToolUse 훅: 편집한 파일 종류에 맞는 정적 검사와 단위 테스트를 실행한다.
# 실패하면 exit 2로 종료하며, stderr 내용이 Claude에게 전달된다.
# DB 테스트는 TEST_DATABASE_URL이 없으면 skip되므로 이 훅에서는 단위 테스트만 돈다.
# 전체 DB 테스트는 README의 자동 검사 명령으로 따로 실행한다.

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
input="$(cat)"
file="$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("file_path", ""))
except Exception:
    print("")')"

case "$file" in
  "$root"/backend/*.py) area=backend ;;
  "$root"/apps/web/*.ts | "$root"/apps/web/*.tsx | "$root"/tests/e2e/*.ts) area=web ;;
  *) exit 0 ;;
esac

fail=0
run() {
  local label="$1"
  shift
  local out
  if ! out="$("$@" 2>&1)"; then
    printf '[훅 실패] %s\n%s\n' "$label" "$(printf '%s\n' "$out" | tail -40)" >&2
    fail=1
  fi
}

# 테스트 환경 변수가 새어 들어와 운영 DB를 건드리지 않게 한다.
unset TEST_DATABASE_URL

if [ "$area" = backend ]; then
  cd "$root" || exit 0
  py=backend/.venv/bin
  run "ruff check" "$py/ruff" check backend
  run "ruff format --check" "$py/ruff" format --check backend
  run "mypy" "$py/mypy" --config-file backend/pyproject.toml backend/src
  run "pytest (DB 없는 단위 테스트)" "$py/pytest" backend/tests -q
else
  run "pnpm lint" pnpm --dir "$root/apps/web" lint
  run "pnpm typecheck" pnpm --dir "$root/apps/web" typecheck
  run "pnpm test" pnpm --dir "$root/apps/web" test
fi

[ "$fail" -eq 0 ] || exit 2
exit 0
