import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Download, Heart, Image as ImageIcon, Info, Music, RefreshCw, Search, Star, Tags, Trash2, Video, X } from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_MEDIA_API_BASE || "";
const ADMIN_BASE_URL = serviceBaseUrl(import.meta.env.VITE_ADMIN_BASE_URL, 8081);
const WEBHARD_BASE_URL = serviceBaseUrl(import.meta.env.VITE_WEBHARD_BASE_URL, 8083);
const PAGE_SIZE = 30;

const TABS = [
  { value: "IMAGE", label: "이미지", icon: ImageIcon },
  { value: "VIDEO", label: "영상", icon: Video },
  { value: "KARAOKE", label: "노래방", icon: Music }
];

const SORT_OPTIONS = [
  { value: "recent", label: "최신순" },
  { value: "popular", label: "조회순" },
  { value: "liked", label: "좋아요순" }
];

function App() {
  const [page, setPage] = useState("media");
  const [items, setItems] = useState([]);
  const [activeKind, setActiveKind] = useState("IMAGE");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  const [counts, setCounts] = useState({ image: 0, video: 0, karaoke: 0 });
  const [hasMore, setHasMore] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [viewerItem, setViewerItem] = useState(null);
  const [currentUser, setCurrentUser] = useState(undefined);
  const [version, setVersion] = useState({ git_commit: "unknown" });
  const sentinelRef = useRef(null);

  useEffect(() => {
    if (page === "media") {
      load({ reset: true });
    }
  }, [page, activeKind, sort, favoriteOnly]);

  useEffect(() => {
    loadCurrentUser();
    loadVersion();
  }, []);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && hasMore && !loading) {
        load({ reset: false });
      }
    }, { rootMargin: "480px 0px" });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loading, items.length, activeKind, sort, query, favoriteOnly]);

  const visibleItems = items;
  const displayCounts = counts;

  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options
    });
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json") ? await response.json() : { message: `HTTP ${response.status}` };
    if (!response.ok || body.ok !== true) {
      throw new Error(body.message || "요청에 실패했습니다.");
    }
    return body.data;
  }

  async function load({ reset = false, nextQuery = query } = {}) {
    const offset = reset ? 0 : items.length;
    setLoading(true);
    setMessage(reset ? "미디어를 불러오는 중입니다." : "추가 미디어를 불러오는 중입니다.");
    try {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(offset),
        sort,
        content_kind: activeKind
      });
      if (nextQuery.trim()) params.set("q", nextQuery.trim());
      if (favoriteOnly) params.set("favorite", "true");
      const data = await request(`/api/media/?${params.toString()}`);
      const nextItems = data.items || [];
      setItems((prev) => reset ? nextItems : mergeItems(prev, nextItems));
      if (data.counts) setCounts(data.counts);
      setHasMore(data.has_more === true);
      setMessage(nextItems.length ? "" : (reset ? "표시할 미디어가 없습니다." : "더 불러올 미디어가 없습니다."));
    } catch (error) {
      if (reset) {
        setItems([]);
        setCounts({ image: 0, video: 0, karaoke: 0 });
        setHasMore(false);
      }
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadVersion() {
    try {
      setVersion(await request("/api/version/"));
    } catch {
      setVersion({ git_commit: "unknown" });
    }
  }

  async function loadCurrentUser() {
    try {
      setCurrentUser(await request("/api/me/"));
    } catch {
      setCurrentUser(null);
    }
  }

  async function sync() {
    setLoading(true);
    setMessage("웹하드 미디어를 동기화하는 중입니다.");
    try {
      const data = await request("/api/sync/", { method: "POST", body: "{}" });
      setMessage(`동기화 완료: ${data.scanned_count}개 확인, ${data.upserted_count}개 반영`);
      await load({ reset: true });
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    postAdminLogout();
    setCurrentUser(null);
    setItems([]);
    setHasMore(false);
    setCounts({ image: 0, video: 0, karaoke: 0 });
    setViewerItem(null);
    setMessage("로그아웃했습니다.");
  }

  async function patchItem(item, patch) {
    try {
      const data = await request(`/api/media/${item.webhard_file_id}/`, {
        method: "PATCH",
        body: JSON.stringify(patch)
      });
      const updated = data.item;
      setItems((prev) => prev.map((entry) => entry.webhard_file_id === updated.webhard_file_id ? updated : entry));
      setViewerItem(updated);
      setMessage("변경 내용을 저장했습니다.");
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function createThumbnail(item) {
    setLoading(true);
    setMessage("썸네일을 생성하는 중입니다.");
    try {
      const data = await request(`/api/media/${item.webhard_file_id}/thumbnail/`, { method: "POST", body: "{}" });
      const updated = data.item;
      if (updated?.webhard_file_id) {
        setItems((prev) => prev.map((entry) => entry.webhard_file_id === updated.webhard_file_id ? updated : entry));
        setViewerItem(updated);
      }
      const updatedCount = Number(data.thumbnail?.updated_count || 0);
      setMessage(updatedCount > 0 || hasVideoThumbnail(updated) ? "썸네일을 반영했습니다." : "생성할 썸네일이 없습니다.");
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function deleteItem(item) {
    if (!window.confirm("이 미디어를 웹하드 휴지통으로 이동할까요?")) {
      return;
    }
    setLoading(true);
    setMessage("미디어를 휴지통으로 이동하는 중입니다.");
    try {
      await request(`/api/media/${item.webhard_file_id}/delete/`, { method: "POST", body: "{}" });
      setItems((prev) => prev.filter((entry) => entry.webhard_file_id !== item.webhard_file_id));
      setViewerItem(null);
      setCounts((prev) => decrementCounts(prev, item));
      setMessage("웹하드 휴지통으로 이동했습니다.");
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  function submitSearch(event) {
    event.preventDefault();
    load({ reset: true });
  }

  function openViewer(item) {
    setViewerItem(item);
    patchItem(item, { increment_view: true });
  }

  return (
    <>
      <header className="topbar">
        <strong>웹하드 미디어</strong>
        <nav>
          {currentUser?.is_admin && <button className={page === "media" ? "topbar-button active" : "topbar-button"} type="button" onClick={() => setPage("media")}>미디어</button>}
          {currentUser?.is_admin && <button className={page === "youtube" ? "topbar-button active" : "topbar-button"} type="button" onClick={() => setPage("youtube")}>유튜브 저장</button>}
          {currentUser && <a href={`${WEBHARD_BASE_URL}/preview.html`} target="_blank" rel="noreferrer">웹하드</a>}
          {currentUser && <a href={`${ADMIN_BASE_URL}/`} target="_blank" rel="noreferrer">어드민</a>}
          {currentUser && <a href={`${ADMIN_BASE_URL}/mypage.do`} target="_blank" rel="noreferrer">마이페이지</a>}
          {currentUser && <button className="topbar-button" type="button" onClick={logout}>로그아웃</button>}
          {currentUser === null && <a className="active" href={loginUrl()}>로그인</a>}
        </nav>
      </header>

      {page === "youtube" ? (
        <YoutubeImportPage
          currentUser={currentUser}
          request={request}
          onImported={(importTags) => {
            setActiveKind(importTags.includes("노래방") ? "KARAOKE" : "VIDEO");
            setPage("media");
          }}
        />
      ) : <main className="shell media-shell">
        <section className="panel page-head">
          <div>
            <h1>{activeKind === "IMAGE" ? "이미지 보기" : activeKind === "KARAOKE" ? "노래방 보기" : "영상 보기"}</h1>
            <p>웹하드에서 동기화된 이미지, 영상, 노래방 영상을 탭으로 분리해 조회합니다.</p>
          </div>
          <div className="actions">
            <button className="btn" type="button" onClick={() => load({ reset: true })} disabled={loading}>
              <RefreshCw size={16} /> 새로고침
            </button>
            {currentUser?.is_admin && <button className="btn primary" type="button" onClick={sync} disabled={loading}>웹하드 동기화</button>}
          </div>
        </section>

        <section className="panel control-panel">
          <div className="tab-row" role="tablist" aria-label="미디어 유형">
            {TABS.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                className={activeKind === value ? "tab-button active" : "tab-button"}
                type="button"
                role="tab"
                aria-selected={activeKind === value}
                onClick={() => setActiveKind(value)}
              >
                <Icon size={17} /> {label} <strong>{tabCount(displayCounts, value)}</strong>
              </button>
            ))}
          </div>

          <form className="filter-row" onSubmit={submitSearch}>
            <label className="search-field">
              검색
              <span className="search-input-wrap">
                <Search size={16} />
                <input className="input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="파일명, 앨범, 태그, 소유자" />
              </span>
            </label>
            <label>
              정렬
              <select className="input" value={sort} onChange={(event) => setSort(event.target.value)}>
                {SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label className="check-control">
              <input type="checkbox" checked={favoriteOnly} onChange={(event) => setFavoriteOnly(event.target.checked)} />
              즐겨찾기만
            </label>
            <button className="btn" type="submit">검색</button>
          </form>
        </section>

        <section className="masonry-grid" aria-label={activeKind === "IMAGE" ? "이미지 목록" : activeKind === "KARAOKE" ? "노래방 목록" : "영상 목록"}>
          {visibleItems.map((item, index) => (
            <MediaCard key={item.webhard_file_id} item={item} index={index} onOpen={openViewer} />
          ))}
        </section>

        {!visibleItems.length && !loading && <div className="empty">조건에 맞는 미디어가 없습니다.</div>}
        <div ref={sentinelRef} className="feed-sentinel">
          {loading ? "불러오는 중입니다." : hasMore ? "아래로 스크롤하면 더 불러옵니다." : "마지막 미디어입니다."}
        </div>
        {message && <p className="message">{message}</p>}
      </main>}

      {viewerItem && (
        <ViewerModal
          item={viewerItem}
          currentUser={currentUser}
          onClose={() => setViewerItem(null)}
          onPatch={patchItem}
          onCreateThumbnail={createThumbnail}
          onDelete={deleteItem}
        />
      )}
      {loading && <LoadingOverlay message={message} />}
      <div className="build-version">media-service · git {version?.git_commit || "unknown"}</div>
    </>
  );
}

function LoadingOverlay({ message }) {
  return (
    <div className="loading-overlay" role="alert" aria-live="assertive" aria-busy="true">
      <div className="loading-box">
        <span className="loading-spinner" />
        <strong>처리 중입니다</strong>
        <p>{message || "잠시만 기다려 주세요."}</p>
      </div>
    </div>
  );
}

function hasVideoThumbnail(item) {
  const thumbnailUrl = String(item?.thumbnail_url || "");
  const contentUrl = String(item?.content_url || "");
  if (!thumbnailUrl) return false;
  if (contentUrl && thumbnailUrl === contentUrl) return false;
  return !thumbnailUrl.includes("/file/content/");
}

function mediaPreviewUrl(item) {
  if (item.content_kind === "VIDEO") {
    return hasVideoThumbnail(item) ? item.thumbnail_url : "";
  }
  return item.thumbnail_url || item.content_url || "";
}

function MediaCard({ item, index, onOpen }) {
  const previewUrl = mediaPreviewUrl(item);
  return (
    <article className={`media-card span-${(index % 5) + 1}`}>
      <button className="card-media" type="button" onClick={() => onOpen(item)}>
        {previewUrl ? <img src={previewUrl} alt="" loading="lazy" /> : <span>미리보기 없음</span>}
        <i>{item.content_kind === "VIDEO" ? <Video size={18} /> : <ImageIcon size={18} />}</i>
      </button>
      <div className="card-meta">
        <strong>{item.title || item.display_name || item.file_name}</strong>
        <small>{item.file_name || item.display_name}</small>
        <div className="tag-row compact">
          {(item.tags || []).slice(0, 3).map((tag) => <span key={tag}>{tag}</span>)}
        </div>
      </div>
    </article>
  );
}

function tabCount(counts, tabValue) {
  if (tabValue === "IMAGE") return counts.image || 0;
  if (tabValue === "KARAOKE") return counts.karaoke || 0;
  return counts.video || 0;
}

function YoutubeImportPage({ currentUser, request, onImported }) {
  const [url, setUrl] = useState("");
  const [tags, setTags] = useState("");
  const [preview, setPreview] = useState(null);
  const [toolStatus, setToolStatus] = useState(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [queueItems, setQueueItems] = useState([]);
  const [jobId, setJobId] = useState("");

  useEffect(() => {
    if (currentUser?.is_admin) {
      checkTools();
    }
  }, [currentUser?.is_admin]);

  useEffect(() => {
    if (!importing || !jobId || !queueItems.length) return undefined;
    let stopped = false;
    const updateQueue = async () => {
      const ids = queueItems.map((item) => item.youtube_video_id).filter(Boolean);
      if (!ids.length) return;
      try {
        const data = await request("/api/youtube/import/status/", {
          method: "POST",
          body: JSON.stringify({ youtube_video_ids: ids, job_id: jobId })
        });
        if (!stopped) {
          if (data.job?.items?.length) {
            updateQueueFromJob(data.job);
          } else {
            markSavedQueueItems(data.items || []);
          }
          if (isYoutubeJobIdle(data.job)) {
            finishImportJob(data.job.result || {});
          }
        }
      } catch {
        // Keep the browser session active while the server-side download continues.
      }
    };
    updateQueue();
    const timer = window.setInterval(updateQueue, 3000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [importing, queueItems.length, jobId]);

  async function checkTools() {
    setLoading(true);
    setMessage("다운로드 도구와 웹하드 상태를 확인하는 중입니다.");
    try {
      const data = await request("/api/youtube/tools/check/", { method: "POST", body: "{}" });
      setToolStatus(data);
      setMessage(data.ok_to_download ? "다운로드와 웹하드 저장 준비가 끝났습니다." : "다운로드 환경 또는 웹하드 상태 확인이 필요합니다.");
      return data;
    } catch (error) {
      setMessage(error.message);
      setToolStatus(null);
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function analyze(event) {
    event.preventDefault();
    setLoading(true);
    setMessage("유튜브 링크를 분석하는 중입니다.");
    setPreview(null);
    setQueueItems([]);
    setJobId("");
    try {
      const data = await request("/api/youtube/preview/", {
        method: "POST",
        body: JSON.stringify({ url })
      });
      setPreview(data);
      setQueueItems(buildImportQueue(data.items || []));
      setMessage(`${data.item_count || 0}개 영상을 찾았습니다.`);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function ensureJob() {
    if (jobId) return jobId;
    const checked = await checkTools();
    if (!checked?.ok_to_download) return "";
    const importTags = splitTags(tags);
    const initialQueue = buildImportQueue(preview?.items || []);
    setLoading(true);
    setMessage("유튜브 저장 작업을 생성하는 중입니다.");
    try {
      const data = await request("/api/youtube/import/", {
        method: "POST",
        body: JSON.stringify({ url, tags: importTags })
      });
      const nextJobId = data.job_id || "";
      if (!nextJobId) {
        setMessage("유튜브 저장 작업을 시작하지 못했습니다.");
        return "";
      }
      setJobId(nextJobId);
      setQueueItems(data.items?.length ? data.items.map(normalizeQueueItem) : initialQueue);
      setMessage(`${data.item_count || initialQueue.length}개 다운로드 작업이 준비되었습니다.`);
      return nextJobId;
    } catch (error) {
      setMessage(error.message);
      return "";
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    const nextJobId = await ensureJob();
    if (!nextJobId) return;
    setImporting(true);
    setLoading(true);
    setQueueItems((current) => current.map((item) => (
      item.status === "saved" ? item : { ...item, status: "downloading", message: "" }
    )));
    setMessage("목록 다운로드를 시작했습니다. 완료 전까지 상태를 계속 확인합니다.");
    try {
      const data = await request("/api/youtube/import/start-all/", {
        method: "POST",
        body: JSON.stringify({ job_id: nextJobId })
      });
      if (data.job?.items?.length) {
        updateQueueFromJob(data.job);
      }
    } catch (error) {
      setMessage(error.message);
      setImporting(false);
    } finally {
      setLoading(false);
    }
  }

  async function startOne(item) {
    const nextJobId = await ensureJob();
    if (!nextJobId) return;
    setImporting(true);
    setQueueItems((current) => current.map((entry) => (
      entry.youtube_video_id === item.youtube_video_id
        ? { ...entry, status: "downloading", message: "" }
        : entry
    )));
    setMessage(`${item.title || item.youtube_video_id} 다운로드를 시작했습니다.`);
    try {
      const data = await request("/api/youtube/import/item/start/", {
        method: "POST",
        body: JSON.stringify({ job_id: nextJobId, youtube_video_id: item.youtube_video_id })
      });
      if (data.job?.items?.length) {
        updateQueueFromJob(data.job);
      }
    } catch (error) {
      setMessage(error.message);
    }
  }

  function finishImportJob(result) {
    const savedCount = result.downloaded_count || result.upserted_count || 0;
    const failedCount = result.failed_count || 0;
    const firstFailure = (result.results || []).find((item) => item.status === "FAILED");
    applyFinalImportResults(result.results || []);
    setMessage(`웹하드 저장 완료: ${result.scanned_count || 0}개 확인, ${savedCount}개 저장, ${failedCount}개 실패${firstFailure?.message ? ` - ${firstFailure.message}` : ""}`);
    setImporting(false);
    setLoading(false);
    if (savedCount > 0) {
      onImported(splitTags(tags));
    }
  }

  function updateQueueFromJob(job) {
    const items = (job.items || []).map(normalizeQueueItem);
    setQueueItems(items);
    const savedCount = items.filter((item) => item.status === "saved").length;
    const failedCount = items.filter((item) => item.status === "failed").length;
    const runningCount = items.filter((item) => item.status === "downloading").length;
    const queuedCount = items.filter((item) => item.status === "queued").length;
    setMessage(`유튜브 저장 진행 중입니다. 저장 ${savedCount}/${items.length}${runningCount ? `, 진행 ${runningCount}` : ""}${queuedCount ? `, 대기 ${queuedCount}` : ""}${failedCount ? `, 실패 ${failedCount}` : ""}`);
  }

  function markSavedQueueItems(savedItems) {
    setQueueItems((current) => {
      const savedById = new Map(savedItems.map((item) => [String(item.youtube_video_id || ""), item]));
      let firstPendingMarked = false;
      const next = current.map((item) => {
        const saved = savedById.get(String(item.youtube_video_id || ""));
        if (saved) {
          return { ...item, status: "saved", webhard_file_id: saved.webhard_file_id };
        }
        if (item.status === "failed") return item;
        if (!firstPendingMarked) {
          firstPendingMarked = true;
          return { ...item, status: "downloading" };
        }
        return { ...item, status: "queued" };
      });
      const savedCount = next.filter((item) => item.status === "saved").length;
      const failedCount = next.filter((item) => item.status === "failed").length;
      setMessage(`유튜브 영상을 다운로드해서 웹하드에 저장하는 중입니다. ${savedCount}/${next.length} 저장${failedCount ? `, ${failedCount} 실패` : ""}`);
      return next;
    });
  }

  function applyFinalImportResults(results) {
    if (!results.length) return;
    const resultById = new Map(results.map((item) => [String(item.youtube_video_id || ""), item]));
    setQueueItems((current) => current.map((item) => {
      const result = resultById.get(String(item.youtube_video_id || ""));
      if (!result) return item;
      if (result.status === "DOWNLOADED") {
        return { ...item, status: "saved", webhard_file_id: result.file_id };
      }
      if (result.status === "FAILED") {
        return { ...item, status: "failed", message: result.message || "저장 실패" };
      }
      return item;
    }));
  }

  if (!currentUser?.is_admin) {
    return (
      <main className="shell media-shell">
        <section className="panel page-head">
          <div>
            <h1>유튜브 저장</h1>
            <p>관리자만 사용할 수 있습니다.</p>
          </div>
        </section>
      </main>
    );
  }

  return (
    <>
      <main className="shell media-shell">
        <section className="panel page-head">
          <div>
            <h1>유튜브 저장</h1>
            <p>단일 영상 또는 재생목록 링크를 다운로드해서 웹하드에 저장하고 미디어 영상 목록에 반영합니다.</p>
          </div>
        </section>

        <section className="panel youtube-panel">
          <div className="tool-check">
            <div>
              <h2>다운로드 환경 체크</h2>
              <p>저장 실행 전 `yt-dlp`, `ffmpeg`, 웹하드 실행 상태를 확인합니다. `ffmpeg`가 없으면 자동 설치합니다.</p>
            </div>
            <button className="btn" type="button" onClick={checkTools} disabled={loading}>다시 체크</button>
          </div>
          {toolStatus && <ToolStatus status={toolStatus} />}
          <form className="youtube-form" onSubmit={analyze}>
            <label>
              유튜브 링크
              <input className="input" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://www.youtube.com/watch?v=... 또는 playlist URL" />
            </label>
            <label>
              태그
              <input className="input" value={tags} onChange={(event) => setTags(event.target.value)} placeholder="쉼표로 구분, 예: 노래방, 최신곡" />
            </label>
            <div className="actions">
              <button className="btn" type="submit" disabled={loading || !url.trim()}>분석</button>
              <button className="btn primary" type="button" onClick={save} disabled={loading || !preview?.item_count}>목록 전체 다운로드 시작</button>
            </div>
          </form>
          {message && <p className="message inline-message">{message}</p>}
        </section>

        {preview && (
          <section className="panel youtube-preview">
            <div className="preview-head">
              <div>
                <h2>{preview.playlist_title || preview.title || "유튜브 영상"}</h2>
                <p>{preview.item_count}개 영상</p>
              </div>
              <button className="btn primary" type="button" onClick={save} disabled={loading}>전체 시작</button>
            </div>
            <QueueSummary items={queueItems} importing={importing} />
            <div className="youtube-list">
              {(queueItems.length ? queueItems : buildImportQueue(preview.items || [])).map((item) => (
                <article className={`youtube-item ${item.status || "queued"}`} key={item.youtube_video_id}>
                  {item.thumbnail_url ? <img src={item.thumbnail_url} alt="" /> : <div className="youtube-thumb-empty">썸네일 없음</div>}
                  <div>
                    <strong>{item.title}</strong>
                    <small>{item.channel_name || item.youtube_video_id}</small>
                    <span className={`queue-status ${item.status || "queued"}`}>{queueStatusLabel(item)}</span>
                    {item.message && <em>{item.message}</em>}
                    <div className="youtube-item-actions">
                      <button
                        className="btn compact"
                        type="button"
                        onClick={() => startOne(item)}
                        disabled={loading || item.status === "downloading" || item.status === "saved"}
                      >
                        개별 다운로드
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
      </main>
      {loading && !importing && <LoadingOverlay message={message} />}
    </>
  );
}

function QueueSummary({ items, importing }) {
  if (!items.length) return null;
  const saved = items.filter((item) => item.status === "saved").length;
  const failed = items.filter((item) => item.status === "failed").length;
  const active = items.some((item) => item.status === "downloading");
  return (
    <div className="queue-summary" aria-live="polite">
      <strong>{saved}/{items.length}</strong>
      <span>{failed ? `${failed}개 실패` : importing || active ? "저장 진행 중" : "저장 대기"}</span>
      <progress max={items.length} value={saved + failed} />
    </div>
  );
}

function ToolStatus({ status }) {
  const tools = status.tools || {};
  return (
    <div className="tool-status-grid">
      {[tools.yt_dlp, tools.ffmpeg, tools.webhard].filter(Boolean).map((tool) => (
        <article className={tool.installed && tool.is_latest !== false ? "tool-card ok" : "tool-card warn"} key={tool.name}>
          <strong>{tool.name}</strong>
          <span>{tool.installed ? "설치됨" : "미설치"}</span>
          <small>현재: {tool.version || "-"}</small>
          <small>최신: {tool.latest_version || "확인 불가"}</small>
          <p>{tool.message}</p>
        </article>
      ))}
    </div>
  );
}

function ViewerModal({ item, currentUser, onClose, onPatch, onCreateThumbnail, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [form, setForm] = useState({ title: item.title || "", album: item.album || "", tags: (item.tags || []).join(", "), description: item.description || "" });
  const canManage = canManageMedia(currentUser, item);
  const canDelete = canDeleteMedia(currentUser, item);

  useEffect(() => {
    setForm({ title: item.title || "", album: item.album || "", tags: (item.tags || []).join(", "), description: item.description || "" });
  }, [item]);

  function save() {
    onPatch(item, {
      title: form.title,
      album: form.album,
      tags: form.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
      description: form.description
    });
    setEditing(false);
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal-panel viewer-panel" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <div>
            <span className="kind-badge">{kindLabel(item.content_kind)}</span>
            <h2>{item.title || item.display_name || item.file_name}</h2>
          </div>
          <button className="btn icon-only" type="button" onClick={onClose} aria-label="닫기"><X size={18} /></button>
        </div>

        <div className="viewer-grid">
          <div className="file-viewer media-viewer">
            {item.source_type === "YOUTUBE" && item.youtube_embed_url ? (
              <iframe className="detail-media youtube-frame" src={item.youtube_embed_url} title={item.title || item.display_name || "YouTube"} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowFullScreen />
            ) : item.content_kind === "VIDEO" && item.content_url ? (
              <video className="detail-media" src={item.content_url} poster={hasVideoThumbnail(item) ? item.thumbnail_url : undefined} controls preload="metadata" />
            ) : item.thumbnail_url || item.content_url ? (
              <img className="detail-media" src={item.content_url || item.thumbnail_url} alt="" />
            ) : (
              <div className="document-detail"><strong>미리보기 없음</strong><span>{item.file_name}</span></div>
            )}
          </div>

          <aside className="viewer-side">
            <div className="actions side-actions">
              <button className="btn" type="button" onClick={() => setInfoOpen(true)}><Info size={16} /> 파일 정보</button>
              {canManage && item.content_kind === "VIDEO" && !hasVideoThumbnail(item) && (
                <button className="btn primary" type="button" onClick={() => onCreateThumbnail(item)}>썸네일 만들기</button>
              )}
              <button className={item.favorite ? "btn primary" : "btn"} type="button" onClick={() => onPatch(item, { favorite: !item.favorite })}>
                <Star size={16} /> 즐겨찾기
              </button>
              <button className={item.liked ? "btn primary" : "btn"} type="button" onClick={() => onPatch(item, { liked: !item.liked })}>
                <Heart size={16} /> {formatCount(item.like_count)}
              </button>
              {item.download_url && <a className="btn" href={item.download_url}><Download size={16} /> 다운로드</a>}
              {canDelete && (
                <button className="btn danger" type="button" onClick={() => onDelete(item)}>
                  <Trash2 size={16} /> 삭제
                </button>
              )}
            </div>

            {editing ? (
              <div className="form-grid single-column">
                <label>제목<input className="input" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
                <label>앨범<input className="input" value={form.album} onChange={(event) => setForm({ ...form, album: event.target.value })} /></label>
                <label>태그<input className="input" value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} placeholder="쉼표로 구분" /></label>
                <label>설명<textarea className="input textarea" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
                <div className="actions">
                  <button className="btn" type="button" onClick={() => setEditing(false)}>취소</button>
                  <button className="btn primary" type="button" onClick={save}>저장</button>
                </div>
              </div>
            ) : (
              <div className="meta-block">
                <div className="tag-row">
                  {(item.tags || []).length ? item.tags.map((tag) => <span key={tag}><Tags size={13} />{tag}</span>) : <span>태그 없음</span>}
                </div>
                <p>{item.description || "설명이 없습니다."}</p>
                {canManage && <button className="btn" type="button" onClick={() => setEditing(true)}>메타데이터 수정</button>}
              </div>
            )}
          </aside>
        </div>
        {infoOpen && <FileInfoDialog item={item} onClose={() => setInfoOpen(false)} />}
      </section>
    </div>
  );
}

function FileInfoDialog({ item, onClose }) {
  return (
    <div className="info-dialog-backdrop" onClick={onClose}>
      <section className="info-dialog" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head compact-head">
          <div>
            <span className="kind-badge">정보</span>
            <h2>파일 정보</h2>
          </div>
          <button className="btn icon-only" type="button" onClick={onClose} aria-label="닫기"><X size={18} /></button>
        </div>
        <dl className="status-list compact-grid">
          <div><dt>파일명</dt><dd>{item.file_name || item.display_name || "-"}</dd></div>
          <div><dt>크기</dt><dd>{formatSize(item.file_size)}</dd></div>
          <div><dt>소유자</dt><dd>{item.owner_user_id || "-"}</dd></div>
          <div><dt>생성일</dt><dd>{formatDateTime(item.original_created_at || item.uploaded_at)}</dd></div>
        </dl>
      </section>
    </div>
  );
}

function mergeItems(current, next) {
  const seen = new Set(current.map((item) => String(item.webhard_file_id)));
  return current.concat(next.filter((item) => !seen.has(String(item.webhard_file_id))));
}

function splitTags(value) {
  return String(value || "")
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function buildImportQueue(items) {
  return (items || []).map((item, index) => ({
    youtube_video_id: String(item.youtube_video_id || item.id || index),
    title: item.title || item.youtube_video_id || `영상 ${index + 1}`,
    channel_name: item.channel_name || "",
    thumbnail_url: item.thumbnail_url || "",
    status: "queued",
    message: ""
  }));
}

function normalizeQueueItem(item) {
  const status = String(item.status || "QUEUED").toUpperCase();
  let mappedStatus = "queued";
  if (status === "RUNNING" || status === "DOWNLOADING") mappedStatus = "downloading";
  if (status === "SAVED" || status === "DOWNLOADED") mappedStatus = "saved";
  if (status === "FAILED") mappedStatus = "failed";
  return {
    youtube_video_id: String(item.youtube_video_id || item.id || ""),
    title: item.title || item.youtube_video_id || "영상",
    channel_name: item.channel_name || "",
    thumbnail_url: item.thumbnail_url || "",
    status: mappedStatus,
    webhard_file_id: item.webhard_file_id || item.file_id || "",
    message: item.message || ""
  };
}

function isYoutubeJobIdle(job) {
  if (!job) return false;
  const status = String(job.status || "").toUpperCase();
  if (status === "DONE" || status === "FAILED") return true;
  return !(job.items || []).some((item) => String(item.status || "").toUpperCase() === "RUNNING");
}

function queueStatusLabel(item) {
  if (item.status === "saved") return "저장 완료";
  if (item.status === "downloading") return "다운로드 중";
  if (item.status === "failed") return "실패";
  return "대기 중";
}

function loginUrl() {
  const returnUrl = typeof window === "undefined" ? "" : window.location.href;
  return `${ADMIN_BASE_URL}/service-login-page.do?service_nm=${encodeURIComponent("Media Service")}&return_url=${encodeURIComponent(returnUrl)}`;
}

function postAdminLogout() {
  if (typeof document === "undefined") return;
  const iframeName = "adminLogoutFrame";
  let iframe = document.querySelector(`iframe[name="${iframeName}"]`);
  if (!iframe) {
    iframe = document.createElement("iframe");
    iframe.name = iframeName;
    iframe.hidden = true;
    document.body.appendChild(iframe);
  }
  const form = document.createElement("form");
  form.method = "POST";
  form.action = `${ADMIN_BASE_URL}/logout.json`;
  form.target = iframeName;
  form.style.display = "none";
  document.body.appendChild(form);
  form.submit();
  window.setTimeout(() => form.remove(), 1000);
}

function serviceBaseUrl(configured, localPort) {
  const value = String(configured || "").replace(/\/+$/, "");
  if (value) {
    return value;
  }
  if (typeof window === "undefined") {
    return `http://localhost:${localPort}`;
  }
  const { protocol, hostname, origin } = window.location;
  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return `${protocol}//${hostname}:${localPort}`;
  }
  return origin;
}

function canManageMedia(currentUser, item) {
  if (!currentUser) return false;
  return currentUser.is_admin === true || String(item?.owner_user_id || "") === String(currentUser.user_id || "");
}

function canDeleteMedia(currentUser, item) {
  if (!canManageMedia(currentUser, item)) return false;
  return currentUser.is_admin === true || currentUser.permissions?.delete === true;
}

function decrementCounts(counts, item) {
  const key = item?.content_kind === "IMAGE" ? "image" : ((item?.tags || []).includes("노래방") ? "karaoke" : "video");
  return { ...counts, [key]: Math.max(Number(counts[key] || 0) - 1, 0) };
}

function kindLabel(kind) {
  if (kind === "IMAGE") return "이미지";
  if (kind === "VIDEO") return "영상";
  return String(kind || "-");
}

function formatSize(value) {
  const size = Number(value || 0);
  if (size >= 1024 * 1024 * 1024) return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`;
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${size} B`;
}

function formatCount(value) {
  return Number(value || 0).toLocaleString("ko-KR");
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("ko-KR", { hour12: false });
}

createRoot(document.getElementById("root")).render(<App />);
