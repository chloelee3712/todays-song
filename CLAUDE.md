# CLAUDE.md

이 파일은 Claude Code가 이 저장소에서 작업할 때 참고하는 프로젝트 컨텍스트다.

## 프로젝트 개요
"오늘의 노래 추천(Today's Song)" — SNU '컴퓨팅적 사고/Exploring Computing' 기말 프로젝트이자
밴드 동아리용 음악 추천 커뮤니티 웹앱. 매일 한 곡씩 추천하고 반응·댓글로 소통하며,
지난 추천을 아카이브에서 열람한다.

과목 요건상 **BeautifulSoup/Selenium을 이용한 데이터 수집**이 반드시 포함돼야 한다.
→ 추천 등록 시 Last.fm 트랙 페이지를 BeautifulSoup으로 스크래핑해 장르 태그를 수집하고,
   통계 페이지에서 장르 분포를 분석·시각화하는 흐름으로 충족한다(수집→정제→분석→시각화).

## 기술 스택
- Python / Streamlit (UI, 단일 페이지 라우팅)
- SQLite (songs / reactions / comments)
- requests + BeautifulSoup (Last.fm 장르 수집)
- Plotly (장르 분포 시각화)

## 파일 구조
- `app.py` — 전체 앱 (DB 계층 / 스크래핑 / UI / 라우팅)
- `requirements.txt`
- `.streamlit/config.toml` — Figma 팔레트 기반 핑크 테마

## 실행 / 배포
```bash
pip install -r requirements.txt
streamlit run app.py
```
배포: GitHub(`chloelee3712/todays-song`) push → Streamlit Community Cloud에서 저장소 연결, main file = `app.py`.

## app.py 코드 구조
- DB 계층: `get_conn`, `init_db`, `add_song`, `get_songs_on`, `toggle_reaction`,
  `reaction_counts`, `user_reacted`, `add_comment`, `get_comments`
- 수집: `fetch_lastfm_genre(artist, title)` — `@st.cache_data`, `a[href^="/tag/"]` 링크 파싱
- UI: `login_view`, `sidebar`, `render_card`, `home_view`, `create_view`, `archive_view`, `stats_view`
- 라우팅: `st.session_state.page` 기반, 사이드바 버튼으로 전환

## 코드 관례 (수정 시 지킬 것)
- 날짜·시간은 항상 `now_kst()` 사용. Streamlit Cloud는 UTC라 KST로 고정하지 않으면 '오늘'이 어긋난다.
- 새 페이지 추가 = 사이드바 버튼 1개 + 라우팅 분기 1개 + `*_view()` 함수 1개 세트.
- DB 접근은 항상 `get_conn()`으로 열고 명시적으로 `close()`.
- 반응은 `(song_id, nickname, kind)` UNIQUE — 누르면 추가, 다시 누르면 취소(토글).
- 버튼/입력 위젯 key는 `f"..._{song['id']}"`로 곡마다 고유하게.

## 현재 상태
- [완료] 로그인 · 타임라인 · 추천 작성 · 24h 1곡 제한 · 반응 3종 · 댓글 · 아카이브 · 통계
- [완료] Last.fm 장르 수집 (테스트 커버리지 6/6)

## 남은 작업
- 발표용 시드 데이터 스크립트 (과거 추천곡을 미리 채워 아카이브/통계를 풍성하게).
- 위키백과 연도·앨범 보강 — 현재 위키 조회가 비어 있어 '더보기'에 곡 정보를 넣으려면
  검색 매칭/User-Agent를 손봐야 한다.
- 영구 저장: Streamlit Cloud 재시작 시 `songs.db`가 초기화됨 → 외부 DB(Supabase/Postgres 등) 검토.
- (장기) 실시간 업데이트를 위한 Flask/FastAPI 이전.

## 주의
- 가사 등 저작권 콘텐츠는 수집·표시하지 않는다. Last.fm에서는 장르 태그·팩트만 사용.
- 사이트 HTML 구조가 바뀌면 `fetch_lastfm_genre`의 선택자(`a[href^="/tag/"]`)를 먼저 점검.
