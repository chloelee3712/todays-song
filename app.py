# -*- coding: utf-8 -*-
"""
오늘의 노래 추천 — 통합 Streamlit 앱
기획서 화면 1~5 + 메타데이터 보강(Last.fm 스크래핑) + 통계/분석 페이지를 하나로 합친 버전.

  화면 1 로그인        : 닉네임만 입력 (회원가입 없음)
  화면 2 홈/타임라인     : 오늘 추천곡 카드 (사용자/곡/아티스트/이유/링크/장르/반응/댓글)
  화면 3 노래 추천 작성  : 곡·아티스트·링크(선택)·이유(필수) → 등록 시 Last.fm에서 장르 자동 수집
  화면 4 댓글           : 각 카드의 '댓글' 펼치기에 통합
  화면 5 아카이브        : 날짜 선택으로 지난 추천곡 열람
  + 통계               : 수집·정제한 장르 데이터를 분석·시각화

[실행]   streamlit run app.py
[배포]   GitHub 푸시 후 Streamlit Community Cloud 연결
※ Streamlit Cloud의 파일시스템은 재시작 시 초기화되므로 songs.db도 리셋됨(데모용으로는 충분).
"""

import re
import urllib.parse
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
import streamlit as st
import plotly.express as px

DB_PATH = "songs.db"
KST = timezone(timedelta(hours=9))   # Streamlit Cloud는 UTC라 한국 날짜로 고정

# (내부키, 이모지, 표시이름)
REACTIONS = [
    ("like", "🩷", "좋아요"),
    ("empathy", "👍", "공감"),
    ("listened", "✨", "들었어요"),
]


def now_kst():
    return datetime.now(KST)


# ======================================================================
# DB 계층
# ======================================================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS songs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nickname TEXT, title TEXT, artist TEXT,
        reason TEXT, link TEXT, genre TEXT, created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS reactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        song_id INTEGER, nickname TEXT, kind TEXT,
        UNIQUE(song_id, nickname, kind))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS comments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        song_id INTEGER, nickname TEXT, body TEXT, created_at TEXT)""")
    conn.commit()
    conn.close()


def user_posted_within_24h(nickname):
    """24시간 1곡 제한 체크."""
    cutoff = (now_kst() - timedelta(hours=24)).isoformat()
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) AS n FROM songs WHERE nickname=? AND created_at > ?",
                     (nickname, cutoff)).fetchone()["n"]
    conn.close()
    return n > 0


def add_song(nickname, title, artist, reason, link, genre):
    conn = get_conn()
    conn.execute("""INSERT INTO songs(nickname,title,artist,reason,link,genre,created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                 (nickname, title, artist, reason, link, genre, now_kst().isoformat()))
    conn.commit()
    conn.close()


def get_songs_on(date_str):
    """date_str='YYYY-MM-DD' (KST 기준) 의 추천곡을 최신순으로."""
    conn = get_conn()
    rows = conn.execute("""SELECT * FROM songs WHERE substr(created_at,1,10)=?
                           ORDER BY created_at DESC""", (date_str,)).fetchall()
    conn.close()
    return rows


def toggle_reaction(song_id, nickname, kind):
    """이미 누른 반응이면 취소, 아니면 추가 (사용자당 반응종류별 1개)."""
    conn = get_conn()
    row = conn.execute("SELECT id FROM reactions WHERE song_id=? AND nickname=? AND kind=?",
                       (song_id, nickname, kind)).fetchone()
    if row:
        conn.execute("DELETE FROM reactions WHERE id=?", (row["id"],))
    else:
        conn.execute("INSERT INTO reactions(song_id,nickname,kind) VALUES(?,?,?)",
                     (song_id, nickname, kind))
    conn.commit()
    conn.close()


def reaction_counts(song_id):
    conn = get_conn()
    rows = conn.execute("""SELECT kind, COUNT(*) AS n FROM reactions
                           WHERE song_id=? GROUP BY kind""", (song_id,)).fetchall()
    conn.close()
    return {r["kind"]: r["n"] for r in rows}


def user_reacted(song_id, nickname):
    conn = get_conn()
    rows = conn.execute("SELECT kind FROM reactions WHERE song_id=? AND nickname=?",
                        (song_id, nickname)).fetchall()
    conn.close()
    return {r["kind"] for r in rows}


def add_comment(song_id, nickname, body):
    conn = get_conn()
    conn.execute("INSERT INTO comments(song_id,nickname,body,created_at) VALUES(?,?,?,?)",
                 (song_id, nickname, body, now_kst().isoformat()))
    conn.commit()
    conn.close()


def get_comments(song_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM comments WHERE song_id=? ORDER BY created_at ASC",
                        (song_id,)).fetchall()
    conn.close()
    return rows


# ======================================================================
# 메타데이터 수집 (Last.fm 트랙 페이지를 BeautifulSoup으로 파싱)
# 같은 곡은 캐시해서 재요청 안 함 (= 정제/효율)
# ======================================================================
def _normalize(s):
    """공백 제거·소문자 변환 후 URL 인코딩 — 대소문자·공백 차이를 흡수."""
    return urllib.parse.quote_plus(re.sub(r"\s+", " ", s.strip()).lower())


@st.cache_data(show_spinner=False, ttl=60 * 60 * 24)
def fetch_lastfm_meta(artist, title):
    """Last.fm 트랙 페이지에서 장르·앨범·청취자 수·재생 수를 스크래핑.
    반환: dict(genre, album, listeners, playcount) — 못 찾은 항목은 None.
    """
    try:
        a = _normalize(artist)
        t = _normalize(title)
        url = f"https://www.last.fm/music/{a}/_/{t}"
        r = requests.get(url, headers={"User-Agent": "OnoChoo/1.0"}, timeout=8)
        if r.status_code != 200:
            return {}
        soup = BeautifulSoup(r.text, "html.parser")

        # ── 장르 태그 ──────────────────────────────────────────────
        tags = []
        for a_tag in soup.select('a[href^="/tag/"]'):
            txt = a_tag.get_text(strip=True)
            if txt and txt.lower() not in [x.lower() for x in tags]:
                tags.append(txt)
        genre = ", ".join(tags[:4]) if tags else None

        # ── 앨범명 ────────────────────────────────────────────────
        album = None
        album_tag = soup.select_one('a[href*="/_/"]')   # /music/Artist/_/Track 패턴 외 앨범 링크
        # 더 정확한 선택자: 트랙 메타 섹션의 앨범
        meta_items = soup.select(".source-album-name, .header-new-crumb")
        for item in meta_items:
            txt = item.get_text(strip=True)
            if txt:
                album = txt
                break
        if not album:
            # fallback: "Album" 레이블 옆 텍스트
            for dt in soup.select("dt"):
                if "album" in dt.get_text(strip=True).lower():
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        album = dd.get_text(strip=True)
                        break

        # ── 청취자 수 / 재생 수 ────────────────────────────────────
        listeners, playcount = None, None
        for abbr in soup.select("abbr.js-abbreviated-counter"):
            val = abbr.get("title", "").replace(",", "")
            label_el = abbr.find_parent()
            label = label_el.get_text(" ", strip=True).lower() if label_el else ""
            if "listener" in label and listeners is None:
                listeners = val
            elif "scrobble" in label or "play" in label:
                playcount = val

        return {"genre": genre, "album": album,
                "listeners": listeners, "playcount": playcount}
    except Exception:
        return {}


# 하위 호환 래퍼 (기존 코드가 genre 문자열을 기대하는 곳에서 사용)
def fetch_lastfm_genre(artist, title):
    return fetch_lastfm_meta(artist, title).get("genre")


# ======================================================================
# UI
# ======================================================================
st.set_page_config(page_title="오늘의 노래 추천", page_icon="🎧", layout="centered")
init_db()

if "nickname" not in st.session_state:
    st.session_state.nickname = None
if "page" not in st.session_state:
    st.session_state.page = "home"


def login_view():
    st.markdown("## 🎧 오늘의 노래 추천")
    st.caption("닉네임만 입력하면 바로 입장 (회원가입 없음)")
    nick = st.text_input("닉네임", max_chars=20, placeholder="예: 은하")
    if st.button("입장하기", type="primary", use_container_width=True):
        if nick.strip():
            st.session_state.nickname = nick.strip()
            st.session_state.page = "home"
            st.rerun()
        else:
            st.warning("닉네임을 입력해줘.")


def sidebar():
    with st.sidebar:
        st.markdown(f"**{st.session_state.nickname}** 님 👋")
        st.divider()
        if st.button("🏠 홈 (타임라인)", use_container_width=True):
            st.session_state.page = "home"; st.rerun()
        if st.button("➕ 노래 추천하기", use_container_width=True):
            st.session_state.page = "create"; st.rerun()
        if st.button("🗂 아카이브", use_container_width=True):
            st.session_state.page = "archive"; st.rerun()
        if st.button("📊 통계", use_container_width=True):
            st.session_state.page = "stats"; st.rerun()
        st.divider()
        if st.button("로그아웃", use_container_width=True):
            st.session_state.nickname = None; st.rerun()


def render_card(song):
    """타임라인/아카이브 공용 추천곡 카드."""
    me = st.session_state.nickname
    with st.container(border=True):
        st.markdown(f"### {song['title']}")
        st.markdown(f"**{song['artist']}**　·　by {song['nickname']}")
        if song["genre"]:
            st.caption(f"🏷 {song['genre']}")
        st.write(song["reason"])
        if song["link"]:
            st.markdown(f"[▶ 들으러 가기]({song['link']})")

        # 반응 버튼 (이미 누른 건 강조)
        counts = reaction_counts(song["id"])
        mine = user_reacted(song["id"], me)
        cols = st.columns(len(REACTIONS))
        for i, (kind, emoji, _label) in enumerate(REACTIONS):
            pressed = kind in mine
            if cols[i].button(f"{emoji} {counts.get(kind, 0)}",
                              key=f"react_{song['id']}_{kind}",
                              use_container_width=True,
                              type="primary" if pressed else "secondary"):
                toggle_reaction(song["id"], me, kind)
                st.rerun()

        # 댓글 (화면 4 통합)
        cmts = get_comments(song["id"])
        with st.expander(f"💬 댓글 {len(cmts)}"):
            for cm in cmts:
                st.markdown(f"**{cm['nickname']}**　·　{cm['created_at'][11:16]}")
                st.write(cm["body"])
                st.divider()
            new = st.text_input("댓글 달기", key=f"cmt_{song['id']}")
            if st.button("등록", key=f"cmtbtn_{song['id']}"):
                if new.strip():
                    add_comment(song["id"], me, new.strip())
                    st.rerun()


def home_view():
    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))
    today = now_kst().strftime("%Y-%m-%d")
    st.markdown("## 🏠 오늘의 추천곡")
    st.caption(f"📅 {today} (KST)")
    songs = get_songs_on(today)
    if not songs:
        st.info("아직 오늘 추천된 곡이 없어. 첫 곡을 추천해볼래?")
    for s in songs:
        render_card(s)
    st.divider()
    if st.button("🎵 오늘의 노래 추천하기", type="primary", use_container_width=True):
        st.session_state.page = "create"; st.rerun()


def create_view():
    me = st.session_state.nickname
    st.markdown("## ➕ 노래 추천하기")
    if user_posted_within_24h(me):
        st.warning("24시간에 한 곡만 추천할 수 있어. 내일 또 와줘! 🌙")
        if st.button("← 홈으로"):
            st.session_state.page = "home"; st.rerun()
        return

    with st.form("recommend"):
        title = st.text_input("곡 제목 *")
        artist = st.text_input("아티스트 *")
        link = st.text_input("스트리밍 링크 (선택)")
        reason = st.text_area("추천 이유 *", height=120)
        submitted = st.form_submit_button("등록", type="primary")

    if submitted:
        if not (title.strip() and artist.strip() and reason.strip()):
            st.error("곡 제목 · 아티스트 · 추천 이유는 필수야.")
            return
        with st.spinner("Last.fm에서 곡 정보를 가져오는 중…"):
            meta = fetch_lastfm_meta(artist, title)
        genre = meta.get("genre")
        add_song(me, title.strip(), artist.strip(), reason.strip(), link.strip(), genre)
        extras = []
        if meta.get("album"):
            extras.append(f"앨범: {meta['album']}")
        if meta.get("listeners"):
            extras.append(f"청취자: {int(meta['listeners']):,}명")
        if meta.get("playcount"):
            extras.append(f"재생: {int(meta['playcount']):,}회")
        extra_str = "  · ".join(extras)
        st.session_state.flash = (
            f"'{title.strip()}' 등록 완료!"
            + (f"  장르: {genre}" if genre else "  (장르 정보 없음)")
            + (f"  |  {extra_str}" if extra_str else "")
        )
        st.session_state.page = "home"
        st.rerun()


def archive_view():
    st.markdown("## 🗂 아카이브")
    st.caption("지난 추천곡을 날짜로 찾아봐")
    d = st.date_input("날짜 선택", value=now_kst().date())
    date_str = d.strftime("%Y-%m-%d")
    songs = get_songs_on(date_str)
    st.markdown(f"**{date_str}** · 추천곡 {len(songs)}곡")
    if not songs:
        st.info("이 날짜엔 추천곡이 없어.")
    for s in songs:
        render_card(s)


def stats_view():
    st.markdown("## 📊 통계 & 장르 분석")
    conn = get_conn()
    songs = conn.execute("SELECT * FROM songs").fetchall()
    total_reactions = conn.execute("SELECT COUNT(*) AS n FROM reactions").fetchone()["n"]
    conn.close()

    if not songs:
        st.info("데이터가 쌓이면 여기에 분석이 나타나.")
        return

    users = {s["nickname"] for s in songs}
    c1, c2, c3 = st.columns(3)
    c1.metric("총 추천곡", len(songs))
    c2.metric("참여자", len(users))
    c3.metric("총 반응", total_reactions)

    # Last.fm로 수집·정제한 장르를 집계 → 시각화
    counter = Counter()
    for s in songs:
        if s["genre"]:
            for g in s["genre"].split(","):
                g = g.strip()
                if g:
                    counter[g] += 1

    if counter:
        data = counter.most_common(10)
        fig = px.bar(
            x=[d[1] for d in data],
            y=[d[0] for d in data],
            orientation="h",
            labels={"x": "추천 수", "y": "장르"},
            title="우리 동아리 최다 추천 장르 TOP 10",
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"최다 장르: **{data[0][0]}** ({data[0][1]}곡)")
    else:
        st.info("아직 장르 정보가 있는 곡이 없어.")


# ----- 라우팅 -----
if st.session_state.nickname is None:
    login_view()
else:
    sidebar()
    page = st.session_state.page
    if page == "home":
        home_view()
    elif page == "create":
        create_view()
    elif page == "archive":
        archive_view()
    elif page == "stats":
        stats_view()
