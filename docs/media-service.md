# 미디어 서비스 설계

## 목표

웹하드에 저장된 이미지/영상 파일을 별도 업로드 없이 갤러리, 앨범, 태그 중심으로 탐색하는 서비스를 만든다.

## 참조형 구조

- 원본 파일: `webhard-service`
- 원본 메타데이터: PostgreSQL `wh_file`
- 미디어 표시/분류 메타데이터: MongoDB `media_items`
- 인증/권한: `admin-service` JWT와 `WEBHARD_SERVICE` 권한 재사용

## 동기화

`POST /api/sync/`는 웹하드 DB에서 활성 이미지/영상 파일을 읽어 MongoDB에 upsert한다.

동기화 대상:

- `content_kind IN ('IMAGE', 'VIDEO')`
- `deleted_yn = 'N'`
- 일반 사용자는 본인 파일만
- 관리자는 전체 사용자 파일

MongoDB 문서 주요 필드:

- `webhard_file_id`
- `owner_user_id`
- `file_name`
- `display_name`
- `file_size`
- `content_type`
- `content_kind`
- `thumbnail_url`
- `content_url`
- `original_created_at`
- `uploaded_at`
- `tags`
- `album`
- `favorite`
- `synced_at`

## 권한

- 조회: `WEBHARD_SERVICE` 권한 중 하나 이상
- 동기화: `WRITE` 권한 또는 관리자
- 메타데이터 수정: 파일 소유자 또는 관리자 + `WRITE`

## 운영 포인트

- MongoDB는 표시용 캐시 성격이므로 장애 시 웹하드 DB에서 재동기화할 수 있다.
- 원본 파일은 웹하드 저장소와 DB를 기준으로 백업한다.
- 미디어 서비스는 웹하드의 `/file/content/:id`, `/file/thumbnail/:id` URL을 그대로 사용한다.

