import streamlit as st
import yfinance as yf
import pandas as pd
import os

# 1. 페이지 설정
st.set_page_config(page_title="맞춤형 & S&P 500 퀀트 스크리너", page_icon="📈", layout="wide")

st.title("📈 커스텀 & S&P 500 퀀트 스크리너 대시보드")
st.caption("대가들의 매매 전략(Minervini, O'Neil, Williams) 기반 맞춤형 분석 시스템")

# 2. 지정 파일(portfolio.csv) 또는 S&P 500 로컬 파일 불러오기 함수
@st.cache_data(ttl=86400)
def load_tickers_from_file(file_path):
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path)
            first_col = df.columns[0]
            tickers = df[first_col].dropna().astype(str).str.strip().str.replace('.', '-', regex=False).tolist()
            return tickers
        except Exception:
            pass
    return []

# 3. 고속 일괄(Batch) 데이터 수집 및 이평선/국면 계산 함수
@st.cache_data(ttl=3600)
def fetch_and_process_data_fast(tickers):
    if not tickers:
        return pd.DataFrame()

    with st.spinner(f"총 {len(tickers)}개 종목 데이터를 분석 중입니다..."):
        df_hist = yf.download(tickers, period="1y", group_by="ticker", threads=True, progress=False)

    all_data = []

    for ticker in tickers:
        ticker = ticker.strip().upper()
        try:
            if len(tickers) == 1:
                stock_data = df_hist
            else:
                if ticker not in df_hist.columns.levels[0]:
                    continue
                stock_data = df_hist[ticker]

            close = stock_data['Close'].dropna()
            if len(close) < 200:
                continue

            price = float(close.iloc[-1])
            sma200 = float(close.rolling(200).mean().iloc[-1])
            sma100 = float(close.rolling(100).mean().iloc[-1])
            sma50  = float(close.rolling(50).mean().iloc[-1])
            sma20  = float(close.rolling(20).mean().iloc[-1])
            sma9   = float(close.rolling(9).mean().iloc[-1])

            try:
                info = yf.Ticker(ticker).fast_info
                trail_pe = getattr(info, 'trailing_pe', None)
                fwd_pe = getattr(info, 'forward_pe', None)
            except Exception:
                trail_pe, fwd_pe = None, None

            pe_improving = bool(fwd_pe and trail_pe and fwd_pe < trail_pe)

            # 5대 국면 분류 로직
            if (sma200 < sma50) and (sma50 < sma20) and (price > sma50):
                phase = "🟢 [그룹 1] 주도주 정배열"
            elif (sma200 < sma50) and (sma9 > sma20) and (price > sma9):
                phase = "🎯 [그룹 2] 눌림목 반등"
            elif (sma200 < sma50) and (price <= sma20 or sma9 <= sma20):
                phase = "🟡 [그룹 3] 조정 관망대기"
            elif (sma50 < sma200) and (price > sma20 and sma9 > sma20):
                phase = "🟠 [그룹 4] 바닥 탈출/턴어라운드"
            else:
                phase = "🔴 [그룹 5] 완벽한 역배열/하락세"

            # 외부 사이트 링크 생성
            yahoo_link = f"https://finance.yahoo.com/quote/{ticker}"
            seeking_alpha_link = f"https://seekingalpha.com/symbol/{ticker}"

            all_data.append({
                "티커": ticker,
                "Yahoo": yahoo_link,
                "SeekingAlpha": seeking_alpha_link,
                "현재가": round(price, 2),
                "국면분류": phase,
                "SMA9": round(sma9, 2),
                "SMA20": round(sma20, 2),
                "SMA50": round(sma50, 2),
                "SMA100": round(sma100, 2),
                "SMA200": round(sma200, 2),
                "Trailing_PE": round(trail_pe, 2) if trail_pe else None,
                "Forward_PE": round(fwd_pe, 2) if fwd_pe else None,
                "PER_개선": pe_improving,
                "diff_sma9": abs((price - sma9) / sma9) * 100,
                "diff_sma20": abs((price - sma20) / sma20) * 100,
                "diff_sma50": abs((price - sma50) / sma50) * 100,
                "diff_sma100": abs((price - sma100) / sma100) * 100,
                "diff_sma200": abs((price - sma200) / sma200) * 100,
            })
        except Exception:
            continue

    return pd.DataFrame(all_data)

# ------------------------------------------------------------------
# 공통 테이블 출력 함수 (링크 컬럼 설정 적용)
# ------------------------------------------------------------------
def display_styled_dataframe(df_to_show, columns_to_display):
    column_config = {
        "Yahoo": st.column_config.LinkColumn(
            "Yahoo",
            display_text="📈 야후",
            help="야후 파이낸스 차트 및 상세 정보로 이동합니다."
        ),
        "SeekingAlpha": st.column_config.LinkColumn(
            "SeekingAlpha",
            display_text="📰 시킹알파",
            help="시킹알파 뉴스 및 기업 분석 정보로 이동합니다."
        )
    }
    st.dataframe(
        df_to_show[columns_to_display],
        column_config=column_config,
        use_container_width=True
    )

# ------------------------------------------------------------------
# 사이드바 설정
# ------------------------------------------------------------------
st.sidebar.header("⚙️ 스크리닝 대상 설정")

portfolio_path = "portfolio.csv"
has_portfolio = os.path.exists(portfolio_path)

if has_portfolio:
    options = ("📂 지정 파일 (portfolio.csv)", "S&P 500 전체 종목", "📁 직접 CSV 파일 업로드", "✏️ 텍스트 입력")
else:
    options = ("S&P 500 전체 종목", "📁 직접 CSV 파일 업로드", "✏️ 텍스트 입력")

mode = st.sidebar.radio("분석 방식을 선택하세요:", options)

target_tickers = []

if mode == "📂 지정 파일 (portfolio.csv)":
    target_tickers = load_tickers_from_file(portfolio_path)
    st.sidebar.success(f"깃허브 `portfolio.csv`에서 {len(target_tickers)}개 종목을 불러왔습니다.")

elif mode == "S&P 500 전체 종목":
    target_tickers = load_tickers_from_file("sp500_tickers.csv")
    if not target_tickers:
        target_tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "TSLA", "AVGO", "LLY"]
    st.sidebar.info(f"S&P 500 구성 종목 {len(target_tickers)}개를 분석합니다.")

elif mode == "📁 직접 CSV 파일 업로드":
    uploaded_file = st.sidebar.file_uploader("티커가 담긴 CSV 파일을 올려주세요", type=["csv"])
    if uploaded_file is not None:
        try:
            user_df = pd.read_csv(uploaded_file)
            first_col = user_df.columns[0]
            target_tickers = user_df[first_col].dropna().astype(str).str.strip().str.replace('.', '-', regex=False).tolist()
            st.sidebar.success(f"파일에서 {len(target_tickers)}개 티커를 읽었습니다.")
        except Exception:
            st.sidebar.error("파일을 읽는 중 오류가 발생했습니다.")
    else:
        st.sidebar.caption("💡 첫 번째 열에 티커 목록이 담긴 CSV 파일을 업로드하세요.")

else: # 텍스트 입력
    custom_input = st.sidebar.text_area(
        "티커를 쉼표(,)나 줄바꿈으로 구분해 입력하세요:",
        value="TSLA, PLTR, NVDA, AMD, QQQ, SPY, COIN",
        height=120
    )
    target_tickers = [t.strip() for t in custom_input.replace('\n', ',').split(',') if t.strip()]
    st.sidebar.success(f"입력된 {len(target_tickers)}개 종목을 분석합니다.")

# 데이터 수집 및 분석 실행
if target_tickers:
    df = fetch_and_process_data_fast(target_tickers)
else:
    df = pd.DataFrame()

# 상단 알림 및 갱신 버튼
if not df.empty:
    st.success(f"총 {len(df)}개 종목 분석 완료!")
    if st.button("🔄 데이터 강제 갱신", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
else:
    if mode == "📁 직접 CSV 파일 업로드" and not target_tickers:
        st.info("좌측 사이드바에서 CSV 파일을 업로드해주세요.")
    else:
        st.warning("분석할 종목 데이터가 없거나 수집 중 오류가 발생했습니다.")
    st.stop()

# ------------------------------------------------------------------
# 탭 구성
# ------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "🏆 전략 1: 미너비니 정배열", 
    "🎯 전략 2: 오닐 눌림목 반등", 
    "📍 전략 3: 이평선별 근접 종목",
    "📊 탭 4: 시장 국면 종합 분류"
])

# TAB 1: 미너비니 정배열
with tab1:
    st.subheader("전략 1. 미너비니 트렌드 템플릿 (상승 추세 정배열)")
    st.caption("**조건**: `200일선 < 50일선 < 20일선` (장·중·단기 정배열) AND `주가 > 50일선`")
    
    res1 = df[df["국면분류"] == "🟢 [그룹 1] 주도주 정배열"]
    cols = ["티커", "Yahoo", "SeekingAlpha", "현재가", "SMA20", "SMA50", "SMA200", "PER_개선", "Trailing_PE", "Forward_PE"]
    
    if not res1.empty:
        display_styled_dataframe(res1, cols)
    else:
        st.info("현재 상승 추세 정배열 조건을 만족하는 종목이 없습니다.")

# TAB 2: 오닐 눌림목 반등
with tab2:
    st.subheader("전략 2. 오닐 & 와인스타인 눌림목 반등 타점")
    st.caption("**조건**: `200일선 < 50일선` (우상향 추세) AND `9일선 > 20일선` (단기 반등 골든크로스) AND `주가 > 9일선`")
    
    res2 = df[df["국면분류"] == "🎯 [그룹 2] 눌림목 반등"]
    cols = ["티커", "Yahoo", "SeekingAlpha", "현재가", "SMA9", "SMA20", "SMA50", "PER_개선", "Trailing_PE", "Forward_PE"]
    
    if not res2.empty:
        display_styled_dataframe(res2, cols)
    else:
        st.info("현재 눌림목 후 단기 반등 조건을 만족하는 종목이 없습니다.")

# TAB 3: 이평선별 근접 종목
with tab3:
    st.subheader("전략 3. 각 이동평균선 근처(±3% 이내) 종목")
    st.caption("주가가 이동평균선에 바짝 붙은 종목을 모바일 화면에 맞춰 순차적으로 보여줍니다.")

    cols_tab3 = ["티커", "Yahoo", "SeekingAlpha", "현재가", "국면분류", "Forward_PE"]

    st.markdown("### 🔹 200일선 근접 (장기 지지선)")
    near_200 = df[df["diff_sma200"] <= 3.0].sort_values(by="diff_sma200")
    if not near_200.empty:
        display_styled_dataframe(near_200, cols_tab3 + ["SMA200"])
    else:
        st.write("근접 종목 없음")
    st.divider()

    st.markdown("### 🔹 100일선 근접 (중장기 허리선)")
    near_100 = df[df["diff_sma100"] <= 3.0].sort_values(by="diff_sma100")
    if not near_100.empty:
        display_styled_dataframe(near_100, cols_tab3 + ["SMA100"])
    else:
        st.write("근접 종목 없음")
    st.divider()

    st.markdown("### 🔹 50일선 근접 (기관 수급선)")
    near_50 = df[df["diff_sma50"] <= 3.0].sort_values(by="diff_sma50")
    if not near_50.empty:
        display_styled_dataframe(near_50, cols_tab3 + ["SMA50"])
    else:
        st.write("근접 종목 없음")
    st.divider()

    st.markdown("### 🔹 20일선 근접 (단기 생명선)")
    near_20 = df[df["diff_sma20"] <= 3.0].sort_values(by="diff_sma20")
    if not near_20.empty:
        display_styled_dataframe(near_20, cols_tab3 + ["SMA20"])
    else:
        st.write("근접 종목 없음")
    st.divider()

    st.markdown("### 🔹 9일선 근접 (극단기 모멘텀선)")
    near_9 = df[df["diff_sma9"] <= 3.0].sort_values(by="diff_sma9")
    if not near_9.empty:
        display_styled_dataframe(near_9, cols_tab3 + ["SMA9"])
    else:
        st.write("근접 종목 없음")

# TAB 4: 시장 국면 종합 분류 및 건강도 분석
with tab4:
    st.subheader("📊 시장 국면 종합 분석 & 건강도 지표")
    st.caption("전체 분석 대상 종목을 5가지 국면으로 나누어 시장 전체의 매수/관망/하락 에너지를 파악합니다.")

    counts = df["국면분류"].value_counts()
    total_len = len(df)

    c1, c2, c3, c4, c5 = st.columns(5)
    g1_cnt = counts.get("🟢 [그룹 1] 주도주 정배열", 0)
    g2_cnt = counts.get("🎯 [그룹 2] 눌림목 반등", 0)
    g3_cnt = counts.get("🟡 [그룹 3] 조정 관망대기", 0)
    g4_cnt = counts.get("🟠 [그룹 4] 바닥 탈출/턴어라운드", 0)
    g5_cnt = counts.get("🔴 [그룹 5] 완벽한 역배열/하락세", 0)

    c1.metric("🟢 정배열 주도주", f"{g1_cnt}개", f"{round(g1_cnt/total_len*100, 1)}%")
    c2.metric("🎯 눌림목 반등", f"{g2_cnt}개", f"{round(g2_cnt/total_len*100, 1)}%")
    c3.metric("🟡 조정 관망대기", f"{g3_cnt}개", f"{round(g3_cnt/total_len*100, 1)}%")
    c4.metric("🟠 바닥 턴어라운드", f"{g4_cnt}개", f"{round(g4_cnt/total_len*100, 1)}%")
    c5.metric("🔴 하락 추세", f"{g5_cnt}개", f"{round(g5_cnt/total_len*100, 1)}%")

    st.divider()

    selected_phase = st.selectbox(
        "조회할 그룹을 선택하세요:",
        options=[
            "전체 보기",
            "🟢 [그룹 1] 주도주 정배열",
            "🎯 [그룹 2] 눌림목 반등",
            "🟡 [그룹 3] 조정 관망대기",
            "🟠 [그룹 4] 바닥 탈출/턴어라운드",
            "🔴 [그룹 5] 완벽한 역배열/하락세"
        ]
    )

    if selected_phase == "전체 보기":
        filtered_df = df
    else:
        filtered_df = df[df["국면분류"] == selected_phase]

    st.markdown(f"**해당 그룹 종목 목록 ({len(filtered_df)}개)**")
    cols_tab4 = ["티커", "Yahoo", "SeekingAlpha", "국면분류", "현재가", "SMA20", "SMA50", "SMA200", "PER_개선", "Forward_PE"]
    display_styled_dataframe(filtered_df, cols_tab4)
