import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { RefreshCw, Search, Star, Tags, Video, Image as ImageIcon } from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_MEDIA_API_BASE || "";

function App() {
  const [items, setItems] = useState([]);
  const [albums, setAlbums] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ q: "", content_kind: "", tag: "", album: "", favorite: false });

  useEffect(() => {
    load();
    loadAlbums();
  }, []);

  const stats = useMemo(() => {
    const images = items.filter((item) => item.content_kind === "IMAGE").length;
    const videos = items.filter((item) => item.content_kind === "VIDEO").length;
    return { total: items.length, images, videos };
  }, [items]);

  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options
    });
    const body = await response.json();
    if (!response.ok || body.ok !== true) {
      throw new Error(body.message || "요청에 실패했습니다.");
    }
    return body.data;
  }

  async function load(nextFilters = filters) {
    setLoading(true);
    setMessage("불러오는 중입니다.");
    try {
      const params = new URLSearchParams();
      Object.entries(nextFilters).forEach(([key, value]) => {
        if (value) params.set(key, String(value));
      });
      const data = await request(`/api/media/?${params.toString()}`);
      setItems(data.items || []);
      setMessage(`${data.items?.length || 0}개 표시 중`);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadAlbums() {
    try {
      const data = await request("/api/albums/");
      setAlbums(data.items || []);
    } catch {
      setAlbums([]);
    }
  }

  async function sync() {
    setLoading(true);
    setMessage("웹하드 미디어를 동기화하고 있습니다.");
    try {
      const data = await request("/api/sync/", { method: "POST", body: "{}" });
      setMessage(`동기화 완료: ${data.scanned_count}개 확인, ${data.upserted_count}개 반영`);
      await load();
      await loadAlbums();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  function updateFilter(name, value) {
    const next = { ...filters, [name]: value };
    setFilters(next);
    load(next);
  }

  async function saveMeta(item, patch) {
    try {
      const data = await request(`/api/media/${item.webhard_file_id}/`, {
        method: "PATCH",
        body: JSON.stringify(patch)
      });
      setItems((prev) => prev.map((entry) => entry.webhard_file_id === item.webhard_file_id ? data.item : entry));
      await loadAlbums();
    } catch (error) {
      setMessage(error.message);
    }
  }

  return (
    <main className="app-shell">
      <section className="toolbar">
        <div>
          <p className="eyebrow">webhard reference media</p>
          <h1>미디어 갤러리</h1>
        </div>
        <button className="primary-button" onClick={sync} disabled={loading}>
          <RefreshCw size={18} />
          동기화
        </button>
      </section>

      <section className="summary-strip">
        <Metric label="전체" value={`${stats.total}개`} />
        <Metric label="이미지" value={`${stats.images}개`} icon={<ImageIcon size={16} />} />
        <Metric label="영상" value={`${stats.videos}개`} icon={<Video size={16} />} />
        <div className="status-line">{message}</div>
      </section>

      <section className="filter-bar">
        <label>
          <Search size={16} />
          <input value={filters.q} onChange={(event) => setFilters({ ...filters, q: event.target.value })} onKeyDown={(event) => event.key === "Enter" && load()} placeholder="파일명, 태그, 앨범" />
        </label>
        <select value={filters.content_kind} onChange={(event) => updateFilter("content_kind", event.target.value)}>
          <option value="">전체 유형</option>
          <option value="IMAGE">이미지</option>
          <option value="VIDEO">영상</option>
        </select>
        <select value={filters.album} onChange={(event) => updateFilter("album", event.target.value)}>
          <option value="">전체 앨범</option>
          {albums.map((album) => <option key={album} value={album}>{album}</option>)}
        </select>
        <label className="check">
          <input type="checkbox" checked={filters.favorite} onChange={(event) => updateFilter("favorite", event.target.checked)} />
          즐겨찾기
        </label>
      </section>

      <section className="media-grid">
        {items.map((item) => (
          <MediaCard key={item.webhard_file_id} item={item} onSave={saveMeta} />
        ))}
      </section>
    </main>
  );
}

function Metric({ label, value, icon }) {
  return (
    <article className="metric">
      <span>{icon}{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function MediaCard({ item, onSave }) {
  const [album, setAlbum] = useState(item.album || "");
  const [tags, setTags] = useState((item.tags || []).join(", "));

  useEffect(() => {
    setAlbum(item.album || "");
    setTags((item.tags || []).join(", "));
  }, [item]);

  return (
    <article className="media-card">
      <a className="media-frame" href={item.content_url} target="_blank" rel="noreferrer">
        {item.content_kind === "VIDEO" ? (
          <video src={item.content_url} poster={item.thumbnail_url} muted preload="metadata" />
        ) : (
          <img src={item.thumbnail_url} alt="" loading="lazy" />
        )}
        <span className="kind-chip">{item.content_kind === "VIDEO" ? "영상" : "이미지"}</span>
      </a>
      <div className="media-info">
        <div className="media-title">
          <strong>{item.display_name || item.file_name}</strong>
          <button className={item.favorite ? "icon-button is-active" : "icon-button"} onClick={() => onSave(item, { favorite: !item.favorite })} title="즐겨찾기">
            <Star size={17} />
          </button>
        </div>
        <span>{formatDate(item.original_created_at)} · {formatSize(item.file_size)}</span>
        <label>
          앨범
          <input value={album} onChange={(event) => setAlbum(event.target.value)} onBlur={() => onSave(item, { album })} />
        </label>
        <label>
          <Tags size={14} />
          <input value={tags} onChange={(event) => setTags(event.target.value)} onBlur={() => onSave(item, { tags })} placeholder="태그 쉼표 구분" />
        </label>
      </div>
    </article>
  );
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString("ko-KR");
}

function formatSize(value) {
  const size = Number(value || 0);
  if (size >= 1024 * 1024 * 1024) return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`;
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${size} B`;
}

createRoot(document.getElementById("root")).render(<App />);

