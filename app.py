import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
import os

# ============================================================
# 데이터베이스 설정
# ============================================================
DB_PATH = "songs.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            link TEXT,
            reason TEXT NOT NULL,
            genre TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            song_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reaction_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(song_id, user_id, reaction_type),
            FOREIGN KEY (song_id) REFERENCES songs(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            song_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (song_id) REFERENCES songs(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ============================================================
# 유틸 함수
# ============================================================
def get_or_create_user(nickname):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE nickname = ?", (nickname,))
    row = c.fetchone()
    if row:
        user_id = row["id"]
    else:
        c.execute("INSERT INTO users (nickname) VALUES (?)", (nickname,))
        conn.commit()
        user_id = c.lastrowid
    conn.close()
    return user_id

def has_recommended_today(user_id):
    conn = get_conn()
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute(
        "SELECT COUNT(*) as cnt FROM songs WHERE user_id = ? AND DATE(created_at) = ?",
        (user_id, today)
    )
    count = c.fetchone()["cnt"]
    conn.close()
    return count > 0

def add_song(user_id, title, artist, link, reason, genre):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO songs (user_id, title, artist, link, reason, genre) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, title, artist, link, reason, genre)
    )
    conn.commit()
    conn.close()

def get_songs_by_date(target_date):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT s.id, s.title, s.artist, s.link, s.reason, s.genre, s.created_at,
               u.nickname
        FROM songs s
        JOIN users u ON s.user_id = u.id
        WHERE DATE(s.created_at) = ?
        ORDER BY s.created_at DESC
    """, (target_date,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_all_songs():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT s.id, s.title, s.artist, s.link, s.reason, s.genre, s.created_at,
               u.nickname
        FROM songs s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.created_at DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_reactions(song_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT reaction_type, COUNT(*) as cnt
        FROM reactions WHERE song_id = ?
        GROUP BY reaction_type
    """, (song_id,))
    result = {row["reaction_type"]: row["cnt"] for row in c.fetchall()}
    conn.close()
    return result

def user_reacted(song_id, user_id, reaction_type):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) as cnt FROM reactions WHERE song_id = ? AND user_id = ? AND reaction_type = ?",
        (song_id, user_id, reaction_type)
    )
    exists = c.fetchone()["cnt"] > 0
    conn.close()
    return exists

def toggle_reaction(song_id, user_id, reaction_type):
    conn = get_conn()
    c = conn.cursor()
    if user_reacted(song_id, user_id, reaction_type):
        c.execute(
            "DELETE FROM reactions WHERE song_id = ? AND user_id = ? AND reaction_type = ?",
            (song_id, user_id, reaction_type)
        )
    else:
        c.execute(
            "INSERT OR IGNORE INTO reactions (song_id, user_id, reaction_type) VALUES (?, ?, ?)",
            (song_id, user_id, reaction_type)
        )
    conn.commit()
    conn.close()

def get_comments(song_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT c.content, c.created_at, u.nickname
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.song_id = ?
        ORDER BY c.created_at ASC
    """, (song_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def add_comment(song_id, user_id, content):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO comments (song_id, user_id, content) VALUES (?, ?, ?)",
        (song_id, user_id, content)
    )
    conn.commit()
    conn.close()

def get_comment_count(song_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM comments WHERE song_id = ?", (song_id,))
    count = c.fetchone()["cnt"]
    conn.close()
    return count

def get_available_dates():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT DATE(created_at) as d FROM songs ORDER BY d DESC")
    dates = [row["d"] for row in c.fetchall()]
    conn.close()
    return dates

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="🎵 오늘의 노래",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS
st.markdown("""
<style>
    .song-card {
        background: linear-gradient(135deg, #667eea11, #764ba211);
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
    }
    .song-title {
        font-size: 1.2em;
        font-weight: bold;
        color: #333;
    }
    .song-artist {
        color: #666;
        font-size: 0.95em;
    }
    .song-reason {
        background: #f8f9fa;
        border-left: 3px solid #667eea;
        padding: 8px 12px;
        margin: 8px 0;
        border-radius: 0 6px 6px 0;
        font-style: italic;
        color: #555;
    }
    .song-meta {
        color: #999;
        font-size: 0.8em;
    }
    .comment-box {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 6px 0;
    }
    .stat-card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e, #16213e);
    }
    div[data-testid="stSidebar"] * {
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 세션 상태 초기화
# ============================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "nickname" not in st.session_state:
    st.session_state.nickname = ""
if "page" not in st.session_state:
    st.session_state.page = "home"
if "view_comments_for" not in st.session_state:
    st.session_state.view_comments_for = None

# ============================================================
# 로그인 화면
# ============================================================
def show_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("")
        st.markdown("")
        st.markdown("<h1 style='text-align:center;'>🎵 오늘의 노래</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#666; font-size:1.1em;'>매일 한 곡, 당신의 음악을 공유하세요</p>", unsafe_allow_html=True)
        st.markdown("---")

        nickname = st.text_input("닉네임을 입력하세요", placeholder="예: 음악좋아")

        if st.button("🎶 입장하기", use_container_width=True, type="primary"):
            if nickname.strip():
                user_id = get_or_create_user(nickname.strip())
                st.session_state.logged_in = True
                st.session_state.user_id = user_id
                st.session_state.nickname = nickname.strip()
                st.rerun()
            else:
                st.error("닉네임을 입력해주세요!")

        st.markdown("")
        st.markdown("""
        <div style='text-align:center; color:#999; font-size:0.85em;'>
            하루에 한 곡만 추천할 수 있어요.<br>
            다른 사람의 추천곡에 반응하고 댓글을 남겨보세요!
        </div>
        """, unsafe_allow_html=True)

# ============================================================
# 곡 카드 표시
# ============================================================
def show_song_card(song, show_actions=True):
    song_id = song["id"]
    reactions = get_reactions(song_id)
    like_cnt = reactions.get("like", 0)
    empathy_cnt = reactions.get("empathy", 0)
    listened_cnt = reactions.get("listened", 0)
    comment_cnt = get_comment_count(song_id)

    created = song["created_at"][:16] if song["created_at"] else ""

    st.markdown(f"""
    <div class="song-card">
        <div class="song-title">🎤 {song['title']}</div>
        <div class="song-artist">{song['artist']}  {'· ' + song['genre'] if song.get('genre') else ''}</div>
        <div class="song-reason">💬 "{song['reason']}"</div>
        <div class="song-meta">추천: {song['nickname']} · {created}</div>
    </div>
    """, unsafe_allow_html=True)

    if show_actions:
        cols = st.columns([1, 1, 1, 1, 1, 2])

        with cols[0]:
            liked = user_reacted(song_id, st.session_state.user_id, "like")
            label = f"{'❤️' if liked else '🤍'} {like_cnt}"
            if st.button(label, key=f"like_{song_id}"):
                toggle_reaction(song_id, st.session_state.user_id, "like")
                st.rerun()

        with cols[1]:
            empathed = user_reacted(song_id, st.session_state.user_id, "empathy")
            label = f"{'👍' if empathed else '👍🏻'} {empathy_cnt}"
            if st.button(label, key=f"empathy_{song_id}"):
                toggle_reaction(song_id, st.session_state.user_id, "empathy")
                st.rerun()

        with cols[2]:
            listened = user_reacted(song_id, st.session_state.user_id, "listened")
            label = f"{'✨' if listened else '⭐'} {listened_cnt}"
            if st.button(label, key=f"listened_{song_id}"):
                toggle_reaction(song_id, st.session_state.user_id, "listened")
                st.rerun()

        with cols[3]:
            if st.button(f"💬 {comment_cnt}", key=f"comment_btn_{song_id}"):
                if st.session_state.view_comments_for == song_id:
                    st.session_state.view_comments_for = None
                else:
                    st.session_state.view_comments_for = song_id
                st.rerun()

        with cols[4]:
            if song.get("link") and song["link"].strip():
                st.link_button("🔗 듣기", song["link"])

    # 댓글 영역
    if st.session_state.view_comments_for == song_id:
        show_comments_section(song_id)

# ============================================================
# 댓글 섹션
# ============================================================
def show_comments_section(song_id):
    st.markdown("---")
    comments = get_comments(song_id)

    if comments:
        for c in comments:
            time_str = c["created_at"][:16] if c["created_at"] else ""
            st.markdown(f"""
            <div class="comment-box">
                <strong>{c['nickname']}</strong>
                <span style="color:#999; font-size:0.8em; margin-left:8px;">{time_str}</span>
                <br>{c['content']}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.caption("아직 댓글이 없어요. 첫 댓글을 남겨보세요!")

    col_input, col_btn = st.columns([5, 1])
    with col_input:
        new_comment = st.text_input(
            "댓글 입력", placeholder="댓글을 남겨보세요...",
            key=f"comment_input_{song_id}", label_visibility="collapsed"
        )
    with col_btn:
        if st.button("등록", key=f"comment_submit_{song_id}"):
            if new_comment.strip():
                add_comment(song_id, st.session_state.user_id, new_comment.strip())
                st.rerun()
            else:
                st.warning("댓글을 입력해주세요.")
    st.markdown("---")

# ============================================================
# 홈 (타임라인)
# ============================================================
def show_home():
    today = date.today()
    st.markdown(f"<h2>🎵 오늘의 노래 <span style='color:#999; font-size:0.6em;'>{today.strftime('%Y년 %m월 %d일')}</span></h2>", unsafe_allow_html=True)

    songs = get_songs_by_date(today.isoformat())

    if not songs:
        st.info("아직 오늘 추천된 곡이 없어요. 첫 번째 추천자가 되어보세요! 🎶")
    else:
        st.caption(f"오늘 총 {len(songs)}곡이 추천되었어요")
        for song in songs:
            show_song_card(song)

# ============================================================
# 노래 추천 작성
# ============================================================
def show_recommend():
    st.markdown("<h2>🎤 오늘의 노래 추천하기</h2>", unsafe_allow_html=True)

    if has_recommended_today(st.session_state.user_id):
        st.warning("🎵 오늘은 이미 추천했습니다! 내일 다시 와주세요.")
        st.caption("하루에 한 곡만 추천할 수 있어요.")
        return

    with st.form("recommend_form"):
        title = st.text_input("곡 제목 *", placeholder="예: Flowers")
        artist = st.text_input("아티스트 *", placeholder="예: Miley Cyrus")
        genre = st.selectbox(
            "장르 (선택)",
            ["", "팝", "K-pop", "힙합", "인디", "록", "발라드", "R&B", "일렉트로닉", "재즈", "클래식", "기타"]
        )
        link = st.text_input("스트리밍 링크 (선택)", placeholder="YouTube, Spotify, Melon 등")
        reason = st.text_area("추천 이유 *", placeholder="이 곡을 추천하는 이유를 적어주세요", max_chars=200)

        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("✅ 등록하기", use_container_width=True, type="primary")
        with col2:
            cancelled = st.form_submit_button("❌ 취소", use_container_width=True)

        if submitted:
            if not title.strip() or not artist.strip() or not reason.strip():
                st.error("곡 제목, 아티스트, 추천 이유는 필수입니다!")
            else:
                add_song(
                    st.session_state.user_id,
                    title.strip(), artist.strip(),
                    link.strip(), reason.strip(), genre
                )
                st.success("🎉 추천이 등록되었습니다!")
                st.session_state.page = "home"
                st.rerun()

        if cancelled:
            st.session_state.page = "home"
            st.rerun()

# ============================================================
# 아카이브
# ============================================================
def show_archive():
    st.markdown("<h2>📅 아카이브</h2>", unsafe_allow_html=True)
    st.caption("지난 날짜의 추천곡들을 돌아볼 수 있어요")

    available_dates = get_available_dates()

    if not available_dates:
        st.info("아직 추천된 곡이 없어요.")
        return

    selected_date = st.date_input(
        "날짜 선택",
        value=date.today(),
        max_value=date.today()
    )

    songs = get_songs_by_date(selected_date.isoformat())

    if songs:
        st.markdown(f"**{selected_date.strftime('%Y년 %m월 %d일')}** — {len(songs)}곡")
        for song in songs:
            show_song_card(song)
    else:
        st.info(f"{selected_date.strftime('%Y년 %m월 %d일')}에는 추천된 곡이 없어요.")

# ============================================================
# 추천 통계
# ============================================================
def show_stats():
    st.markdown("<h2>📊 추천 통계</h2>", unsafe_allow_html=True)

    all_songs = get_all_songs()

    if not all_songs:
        st.info("아직 데이터가 부족해요. 곡을 추천해주세요!")
        return

    df = pd.DataFrame(all_songs)
    df["date"] = pd.to_datetime(df["created_at"]).dt.date

    # 기본 통계 카드
    total_songs = len(df)
    total_users = df["nickname"].nunique()
    total_artists = df["artist"].nunique()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🎵 총 추천곡", f"{total_songs}곡")
    with col2:
        st.metric("👤 참여자 수", f"{total_users}명")
    with col3:
        st.metric("🎤 아티스트 수", f"{total_artists}명")

    st.markdown("---")

    # 차트 영역
    tab1, tab2, tab3, tab4 = st.tabs(["장르 분포", "일별 추천 수", "인기 아티스트", "활발한 추천자"])

    with tab1:
        genre_df = df[df["genre"] != ""].copy()
        if len(genre_df) > 0:
            genre_counts = genre_df["genre"].value_counts().reset_index()
            genre_counts.columns = ["장르", "곡 수"]
            fig = px.pie(
                genre_counts, names="장르", values="곡 수",
                title="추천곡 장르 분포",
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig.update_traces(textinfo="label+percent")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("장르 정보가 있는 곡이 아직 없어요.")

    with tab2:
        daily = df.groupby("date").size().reset_index(name="곡 수")
        daily["date"] = pd.to_datetime(daily["date"])
        fig = px.bar(
            daily, x="date", y="곡 수",
            title="일별 추천곡 수",
            labels={"date": "날짜"},
            color_discrete_sequence=["#667eea"]
        )
        fig.update_xaxes(dtick="D1", tickformat="%m/%d")
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        artist_counts = df["artist"].value_counts().head(10).reset_index()
        artist_counts.columns = ["아티스트", "추천 횟수"]
        fig = px.bar(
            artist_counts, x="추천 횟수", y="아티스트",
            orientation="h", title="가장 많이 추천된 아티스트 TOP 10",
            color_discrete_sequence=["#764ba2"]
        )
        fig.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    with tab4:
        user_counts = df["nickname"].value_counts().head(10).reset_index()
        user_counts.columns = ["닉네임", "추천 곡 수"]
        fig = px.bar(
            user_counts, x="추천 곡 수", y="닉네임",
            orientation="h", title="가장 활발한 추천자 TOP 10",
            color_discrete_sequence=["#f093fb"]
        )
        fig.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    # 추천 이유 워드클라우드
    st.markdown("---")
    st.subheader("☁️ 추천 이유 키워드")
    reasons = " ".join(df["reason"].tolist())
    if len(reasons.strip()) > 10:
        try:
            from wordcloud import WordCloud
            import matplotlib.pyplot as plt

            # 한글 폰트 경로 (시스템에 따라 다를 수 있음)
            font_path = None
            possible_fonts = [
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/System/Library/Fonts/AppleGothic.ttf",
            ]
            for fp in possible_fonts:
                if os.path.exists(fp):
                    font_path = fp
                    break

            wc_kwargs = dict(
                width=800, height=300,
                background_color="white",
                colormap="viridis",
                max_words=50,
            )
            if font_path:
                wc_kwargs["font_path"] = font_path

            wc = WordCloud(**wc_kwargs).generate(reasons)
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.imshow(wc, interpolation="bilinear")
            ax.axis("off")
            st.pyplot(fig)
        except Exception as e:
            st.caption(f"워드클라우드 생성 중 오류: {e}")
    else:
        st.caption("추천 이유 데이터가 더 필요해요.")

# ============================================================
# 사이드바 네비게이션
# ============================================================
def show_sidebar():
    with st.sidebar:
        st.markdown(f"### 🎵 오늘의 노래")
        st.markdown(f"안녕하세요, **{st.session_state.nickname}**님!")
        st.markdown("---")

        if st.button("🏠 홈", use_container_width=True):
            st.session_state.page = "home"
            st.session_state.view_comments_for = None
            st.rerun()

        if st.button("🎤 노래 추천하기", use_container_width=True):
            st.session_state.page = "recommend"
            st.session_state.view_comments_for = None
            st.rerun()

        if st.button("📅 아카이브", use_container_width=True):
            st.session_state.page = "archive"
            st.session_state.view_comments_for = None
            st.rerun()

        if st.button("📊 추천 통계", use_container_width=True):
            st.session_state.page = "stats"
            st.session_state.view_comments_for = None
            st.rerun()

        st.markdown("---")

        if st.button("🚪 로그아웃", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.nickname = ""
            st.session_state.page = "home"
            st.session_state.view_comments_for = None
            st.rerun()

        st.markdown("---")
        st.caption("© 2026 오늘의 노래")

# ============================================================
# 샘플 데이터 삽입 (데모용)
# ============================================================
def insert_sample_data():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM songs")
    if c.fetchone()["cnt"] > 0:
        conn.close()
        return

    # 샘플 사용자
    sample_users = ["민지", "하늘", "재현", "수아", "도윤"]
    user_ids = {}
    for name in sample_users:
        user_ids[name] = get_or_create_user(name)

    # 샘플 곡 데이터
    sample_songs = [
        (user_ids["민지"], "Flowers", "Miley Cyrus", "https://open.spotify.com/track/0yLdNVWF3Srea0uzk55zFo", "요즘 기분 업! 강추곡", "팝"),
        (user_ids["하늘"], "Super Shy", "NewJeans", "", "여름 분위기 물씬! 🌊", "K-pop"),
        (user_ids["재현"], "Hype Boy", "NewJeans", "", "중독성 최고", "K-pop"),
        (user_ids["수아"], "Ditto", "NewJeans", "", "감성적인 멜로디가 좋아요", "K-pop"),
        (user_ids["도윤"], "Bohemian Rhapsody", "Queen", "", "록의 전설... 항상 들어도 좋음", "록"),
        (user_ids["민지"], "APT.", "ROSÉ & Bruno Mars", "", "올해의 노래!!", "팝"),
        (user_ids["하늘"], "사랑은 늘 도망가", "임영웅", "", "요즘 이 노래에 빠졌어요", "발라드"),
        (user_ids["재현"], "Butter", "BTS", "", "기분 좋아지는 곡 🧈", "K-pop"),
        (user_ids["수아"], "Blinding Lights", "The Weeknd", "", "새벽 드라이브할 때 최고", "팝"),
        (user_ids["도윤"], "Bad Guy", "Billie Eilish", "", "독특한 분위기가 매력적", "팝"),
        (user_ids["민지"], "Next Level", "aespa", "", "운동할 때 듣기 좋은 곡!", "K-pop"),
        (user_ids["하늘"], "Hotel California", "Eagles", "", "클래식 록의 정수", "록"),
        (user_ids["재현"], "소주 한 잔", "임창정", "", "회식 후 들으면 눈물나요 ㅠㅠ", "발라드"),
        (user_ids["수아"], "Levitating", "Dua Lipa", "", "파티 분위기 낼 때!", "팝"),
        (user_ids["도윤"], "Memories", "Maroon 5", "", "졸업 시즌에 딱인 노래", "팝"),
    ]

    # 날짜를 다양하게 분산
    from datetime import timedelta
    base = datetime.now()
    for i, (uid, title, artist, link, reason, genre) in enumerate(sample_songs):
        days_ago = i % 5
        ts = (base - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "INSERT INTO songs (user_id, title, artist, link, reason, genre, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, title, artist, link, reason, genre, ts)
        )

    # 샘플 반응
    import random
    c.execute("SELECT id FROM songs")
    song_ids = [row["id"] for row in c.fetchall()]
    all_user_ids = list(user_ids.values())
    for sid in song_ids:
        for uid in random.sample(all_user_ids, random.randint(1, 4)):
            rtype = random.choice(["like", "empathy", "listened"])
            c.execute(
                "INSERT OR IGNORE INTO reactions (song_id, user_id, reaction_type) VALUES (?, ?, ?)",
                (sid, uid, rtype)
            )

    # 샘플 댓글
    sample_comments = [
        "좋은 노래네요! 🎶", "이거 저도 좋아해요!", "추천 감사합니다~",
        "처음 들어보는데 좋네요", "중독성 있어요!!", "명곡이죠 ㅎㅎ",
        "플레이리스트에 추가했어요", "이 아티스트 노래 다 좋아요",
    ]
    for sid in random.sample(song_ids, min(8, len(song_ids))):
        for _ in range(random.randint(1, 3)):
            uid = random.choice(all_user_ids)
            content = random.choice(sample_comments)
            c.execute(
                "INSERT INTO comments (song_id, user_id, content) VALUES (?, ?, ?)",
                (sid, uid, content)
            )

    conn.commit()
    conn.close()

# 샘플 데이터 삽입
insert_sample_data()

# ============================================================
# 메인 라우팅
# ============================================================
if not st.session_state.logged_in:
    show_login()
else:
    show_sidebar()

    page = st.session_state.page
    if page == "home":
        show_home()
    elif page == "recommend":
        show_recommend()
    elif page == "archive":
        show_archive()
    elif page == "stats":
        show_stats()
    else:
        show_home()
