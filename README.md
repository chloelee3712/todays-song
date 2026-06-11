# 🎧 오늘의 노래 추천 (Today's Song)

동아리 기반 음악 추천 커뮤니티 웹앱. 매일 한 곡씩 추천하고, 반응·댓글로 소통하고,
지난 추천을 아카이브에서 찾아본다. 추천 등록 시 Last.fm에서 장르를 자동 수집해
통계 페이지에서 분포를 시각화한다.

## 실행
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 배포 (Streamlit Community Cloud)
1. GitHub 저장소(`chloelee3712/todays-song`)에 push
2. https://share.streamlit.io 에서 저장소 연결, **main file = `app.py`**

## 기능
- 닉네임 로그인 (회원가입 없음)
- 오늘의 추천곡 타임라인 (시간순)
- 노래 추천 (24시간 1곡 제한, 등록 시 장르 자동 수집)
- 반응 3종(🩷 좋아요 / 👍 공감 / ✨ 들었어요) 토글 + 개수
- 곡별 댓글
- 날짜별 아카이브
- 통계: 동아리 최다 추천 장르 분석·시각화

## 폴더 구조
```
todays-song/
├── app.py
├── requirements.txt
├── CLAUDE.md
├── .gitignore
└── .streamlit/
    └── config.toml
```

## 메모
- 날짜는 KST(한국시간) 고정.
- Streamlit Cloud는 재시작 시 `songs.db`가 초기화됨(데모용). 영구 저장은 외부 DB 필요.
- 데이터 수집: Last.fm 트랙 페이지를 BeautifulSoup으로 파싱(과목 요건 충족).
