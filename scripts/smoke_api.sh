#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

request() {
  local path="$1"
  curl --fail --silent --show-error "${BASE_URL}${path}"
}

expect_contains() {
  local value="$1"
  local expected="$2"

  if [[ "${value}" != *"${expected}"* ]]; then
    echo "Expected response to contain: ${expected}" >&2
    echo "Response was: ${value}" >&2
    exit 1
  fi
}

health="$(request "/health")"
expect_contains "${health}" '"status":"ok"'

exams="$(request "/api/v1/exams")"
expect_contains "${exams}" '"exam_date":"2025-04"'
expect_contains "${exams}" '"part":"B"'

questions="$(request "/api/v1/questions?exam_date=2025-04&part=B")"
expect_contains "${questions}" '"stable_id":"2025-04_B_001"'
expect_contains "${questions}" '"number":1'

question="$(request "/api/v1/questions/2025-04_B_001")"
expect_contains "${question}" '"stable_id":"2025-04_B_001"'
expect_contains "${question}" '"options"'

review_question="$(request "/api/v1/questions/2025-04_B_001/review")"
expect_contains "${review_question}" '"correct_answer":"'
expect_contains "${review_question}" '"reference":"'

echo "API smoke check passed: ${BASE_URL}"
