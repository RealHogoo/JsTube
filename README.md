# media-service

`media-service`는 `webhard-service`의 이미지/영상 원본을 참조하는 React + Django + MongoDB 기반 미디어 갤러리 서비스입니다.

원본 파일은 웹하드에 그대로 두고, 미디어 서비스는 MongoDB에 표시용 메타데이터만 동기화합니다.

## 구조

- `backend`: Django JSON API
- `frontend`: Vite React UI
- `docs`: 운영/설계 문서

## 주요 기능

- 웹하드 `wh_file`의 `IMAGE`, `VIDEO` 파일 동기화
- MongoDB 기반 미디어 목록 조회
- 날짜, 종류, 태그, 검색어 필터
- 앨범, 태그, 즐겨찾기 메타데이터 수정
- 웹하드 원본/썸네일 URL 참조

## 실행

백엔드:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py runserver 0.0.0.0:8084
```

프론트:

```powershell
cd frontend
npm install
npm run dev
```

프론트 기본 개발 주소는 `http://localhost:5174`입니다.

## API

- `GET /api/health/`
- `GET /api/me/`
- `POST /api/sync/`
- `GET /api/media/`
- `PATCH /api/media/<webhard_file_id>/`
- `GET /api/albums/`

## 문서

- [설계 문서](docs/media-service.md)

