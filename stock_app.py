import streamlit as st
import yfinance as yf
import pandas as pd
import os

# 1. 페이지 설정
st.set_page_config(page_title="맞춤형 & S&P 500 퀀트 스크리너", page_icon="📈", layout="wide")

st.title("📈 커스텀 & S&P 500 퀀트 스크리너 대시보드")
st.caption("대가들의 매매 전략(Minervini, O'Neil, Williams) + 거래량 수급 검증 시스템")

# 2. 파일 내 `#` 주석 형태의 섹터 분류 파싱 함수
@st.cache_data(ttl=86400)
def load_tickers_and_sectors_from_file(file_path):
    """
    파일 내 '# 섹터명' 형태로 작성된 주석을 파싱하여
    (티커 리스트, {티커: 섹터명} 딕셔너리) 튜플을 반환합니다.
    """
    tickers = []
    ticker_sector_map = {}
    
    if os.path.exists(file_path):
        try:
            current_sector = "미분류"
            with open(file_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    
                    # `#`으로 시작하는 경우 섹터명으로 갱신
                    if line_str.startswith('#'):
                        current_sector = line_str.lstrip('#').strip()
                        continue
                    
                    # CSV 행 분할 (첫 번째 컬럼을 티커로 인식)
                    parts = [p.strip() for p in line_str.split(',')]
                    ticker = parts[0].replace('.', '-').upper()
                    
                    # 헤더 행 제외 logic (Ticker, Symbol 등)
                    if ticker in ["TICKER", "SYMBOL", "종목코드"]:
                        continue
                        
                    if ticker:
                        tickers.append(ticker)
                        ticker_sector_map[ticker] = current_sector
        except Exception:
            pass
            
    return tickers, ticker_sector_map

# 3. 고속 일괄(Batch) 데이터 수집 및 이평선/거래량/국면 계산 함수
@st.cache_data(ttl=3600)
def fetch_and_process_data_fast(tickers, file_sector_map=None):
    if not tickers:
        return pd.DataFrame()

    if file_sector_map is None:
        file_sector_map = {}

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
            volume = stock_data['Volume'].dropna()

            if len(close) < 200 or len(volume) < 20:
                continue

            # 1. 가격 및 이동평균선
            price = float(close.iloc[-1])
            sma200 = float(close.rolling(200).mean().iloc[-1])
            sma100 = float(close.rolling(100).mean().iloc[-1])
            sma50  = float(close.rolling(50).mean().iloc[-1])
            sma20  = float(close.rolling(20).mean().iloc[-1])
            sma9   = float(close.rolling(9).mean().iloc[-1])

            # 2. 거래량(Volume) 지표 계산
            curr_vol = float(volume.iloc[-1])
            vol_sma20 = float(volume.rolling(20).mean().iloc[-1])
            vol_sma5  = float(volume.rolling(5).mean().iloc[-1])
            
            # 20일 평균 대비 당일 거래량 비율 (예: 1.2 -> 120%)
            vol_ratio = (curr_vol / vol_sma20) if vol_sma20 > 0 else 0.0

            # 3. 섹터 및 펀더멘털 수집
            # 파일 매핑에 존재하는 섹터가 우선이며, 없을 경우 야후 파이낸스에서 추출
            sector = file_sector_map.get(ticker)
            trail_pe, fwd_pe = None, None

            try:
                t_obj = yf.Ticker(ticker)
                
                # 파일에 섹터 정보가 없으면 yfinance info에서 구함 (예: S&P 500 종목)
                if not sector or sector == "미분류":
                    info_dict = t_obj.info
                    sector = info_dict.get('sector', 'N/A')
                
                fast_info = t_obj.fast_info
                trail_pe = getattr(fast_info, 'trailing_pe', None)
                fwd_pe = getattr(fast_info, 'forward_pe', None)
            except Exception:
                if not sector:
                    sector = "N/A"

            pe_improving = bool(fwd_pe and trail_pe and fwd_pe < trail_pe)

            # 4. 5대 국면 분류 로직
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

            # 외부 링크
            yahoo_link = f"https://finance.yahoo.com/quote/{ticker}"
            seeking_alpha_link = f"https://seekingalpha.com/symbol/{ticker}"

            all_data.append({
                "티커": ticker,
                "섹터": sector,
                "Yahoo": yahoo_link,
                "SeekingAlpha": seeking_alpha_link,
                "현재가": round(price, 2),
                "국면분류": phase,
                "Volume_Ratio": round(vol_ratio, 2),
                "Vol_5일평균": round(vol_sma5, 0),
                "Vol_20일평균": round(vol_sma20, 0),
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
# 공통 테이블 출력 함수
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
        ),
        "Volume_Ratio": st.column_config.NumberColumn(
            "거래량 비율",
            help="20일 평균 거래량 대비 당일 거래량 비율 (1.0 = 100%)",
            format="%.2f"
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
etf_path = "ETF.csv"

has_portfolio = os.path.exists(portfolio_path)
has_etf = os.path.exists(etf_path)

# 옵션 리스트 동적 구성
options = []
if has_portfolio:
    options.append("📂 지정 파일 (portfolio.csv)")
if has_etf:
    options.append("📊 ETF 목록 (ETF.csv)")

options.extend(["S&P 500 전체 종목", "📁 직접 CSV 파일 업로드", "✏️ 텍스트 입력"])

mode = st.sidebar.radio("분석 방식을 선택하세요:", options)

target_tickers = []
file_sector_map = {}

if mode == "📂 지정 파일 (portfolio.csv)":
    target_tickers, file_sector_map = load_tickers_and_sectors_from_file(portfolio_path)
    st.sidebar.success(f"`portfolio.csv`에서 {len(target_tickers)}개 종목을 불러왔습니다.")

elif mode == "📊 ETF 목록 (ETF.csv)":
    target_tickers, file_sector_map = load_tickers_and_sectors_from_file(etf_path)
    st.sidebar.success(f"`ETF.csv`에서 {len(target_tickers)}개 종목을 불러왔습니다.")

elif mode == "S&P 500 전체 종목":
    target_tickers, _ = load_tickers_and_sectors_from_file("sp500_tickers.csv")
    if not target_tickers:
        target_tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "TSLA", "AVGO", "LLY"]
    st.sidebar.info(f"S&P 500 구성 종목 {len(target_tickers)}개를 분석합니다. (야후 파이낸스 섹터 정보 반영)")

elif mode == "📁 직접 CSV 파일 업로드":
    uploaded_file = st.sidebar.file_uploader("티커가 담긴 CSV 파일을 올려주세요", type=["csv"])
    if uploaded_file is not None:
        try:
            # 업로드 파일 파싱 처리
            content = uploaded_file.getvalue().decode('utf-8-sig').splitlines()
            current_sec = "미분류"
            for line in content:
                line_str = line.strip()
                if not line_str:
                    continue
                if line_str.startswith('#'):
                    current_sec = line_str.lstrip('#').strip()
                    continue
                parts = [p.strip() for p in line_str.split(',')]
                t = parts[0].replace('.', '-').upper()
                if t and t not in ["TICKER", "SYMBOL", "종목코드"]:
                    target_tickers.append(t)
                    file_sector_map[t] = current_sec
            st.sidebar.success(f"파일에서 {len(target_tickers)}개 티커를 읽었습니다.")
        except Exception:
            st.sidebar.error("파일을 읽는 중 오류가 발생했습니다.")
    else:
        st.sidebar.caption("💡 티커 목록 및 `# 섹터명` 주석이 담긴 CSV 파일을 업로드하세요.")

else: # 텍스트 입력
    custom_input = st.sidebar.text_area(
        "티커를 쉼표(,)나 줄바꿈으로 구분해 입력하세요 (# 섹터명 지정 가능):",
        value="# Tech\nNVDA, AMD, AAPL, MSFT\n# ETF\nQQQ, SPY",
        height=140
    )
    raw_lines = custom_input.splitlines()
    current_sec = "미분류"
    for line in raw_lines:
        line_str = line.strip()
        if not line_str:
            continue
        if line_str.startswith('#'):
            current_sec = line_str.lstrip('#').strip()
            continue
        items = line_str.replace('\n', ',').split(',')
        for item in items:
            t = item.strip().upper()
            if t:
                target_tickers.append(t)
                file_sector_map[t] = current_sec
    st.sidebar.success(f"입력된 {len(target_tickers)}개 종목을 분석합니다.")

# 데이터 수집 및 분석 실행
if target_tickers:
    df = fetch_and_process_data_fast(target_tickers, file_sector_map)
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
# 탭 구성 (거래량 조건 및 섹터 포함)
# ------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "🏆 전략 1: 미너비니 정배열 + 수급지속", 
    "🎯 전략 2: 오닐 반등 + 거래량 유입", 
    "📍 전략 3: 이평선 근접 + 매물 소진",
    "📊 탭 4: 시장 국면 종합 분류"
])

# TAB 1: 미너비니 정배열 + 거래량 우상향
with tab1:
    st.subheader("전략 1. 미너비니 트렌드 템플릿 (정배열 + 거래량 지속)")
    st.caption("**조건**: `200일선 < 50일선 < 20일선` AND `주가 > 50일선` AND `5일 평균거래량 > 20일 평균거래량`")
    
    cond1 = (df["국면분류"] == "🟢 [그룹 1] 주도주 정배열") & (df["Vol_5일평균"] > df["Vol_20일평균"])
    res1 = df[cond1]
    cols1 = ["티커", "섹터", "Yahoo", "SeekingAlpha", "현재가", "국면분류", "Volume_Ratio", "SMA20", "SMA50", "SMA200", "PER_개선", "Forward_PE"]
    
    if not res1.empty:
        display_styled_dataframe(res1, cols1)
    else:
        st.info("현재 정배열 및 단기 거래량 우상향 조건을 만족하는 종목이 없습니다.")

# TAB 2: 오닐 눌림목 반등 + 거래량 폭발/유입
with tab2:
    st.subheader("전략 2. 오닐 & 와인스타인 눌림목 반등 (수급 유입 타점)")
    st.caption("**조건**: `200일선 < 50일선` AND `9일선 > 20일선` AND `주가 > 9일선` AND `거래량 비율 >= 1.2` (20일 평균 대비 20% 이상 수급 증가)")
    
    cond2 = (df["국면분류"] == "🎯 [그룹 2] 눌림목 반등") & (df["Volume_Ratio"] >= 1.2)
    res2 = df[cond2]
    cols2 = ["티커", "섹터", "Yahoo", "SeekingAlpha", "현재가", "국면분류", "Volume_Ratio", "SMA9", "SMA20", "SMA50", "PER_개선", "Forward_PE"]
    
    if not res2.empty:
        display_styled_dataframe(res2, cols2)
    else:
        st.info("현재 눌림목 후 거래량이 동반된 단기 반등 종목이 없습니다.")

# TAB 3: 이평선 근접 + 거래량 건조(Dry-up)
with tab3:
    st.subheader("전략 3. 각 이동평균선 근처(±3%) + 거래량 소진(Dry-up)")
    st.caption("주가가 지지선 근처에 바짝 붙으면서 **거래량이 20일 평균 이하(Volume_Ratio <= 1.0)**로 줄어들어 매도세가 마른 종목입니다.")

    cols_tab3 = ["티커", "섹터", "Yahoo", "SeekingAlpha", "현재가", "Volume_Ratio", "국면분류", "Forward_PE"]

    st.markdown("### 🔹 200일선 근접 + 거래량 감축")
    near_200 = df[(df["diff_sma200"] <= 3.0) & (df["Volume_Ratio"] <= 1.0)].sort_values(by="diff_sma200")
    if not near_200.empty:
        display_styled_dataframe(near_200, cols_tab3 + ["SMA200"])
    else:
        st.write("조건 만족 종목 없음")
    st.divider()

    st.markdown("### 🔹 100일선 근접 + 거래량 감축")
    near_100 = df[(df["diff_sma100"] <= 3.0) & (df["Volume_Ratio"] <= 1.0)].sort_values(by="diff_sma100")
    if not near_100.empty:
        display_styled_dataframe(near_100, cols_tab3 + ["SMA100"])
    else:
        st.write("조건 만족 종목 없음")
    st.divider()

    st.markdown("### 🔹 50일선 근접 + 거래량 감축")
    near_50 = df[(df["diff_sma50"] <= 3.0) & (df["Volume_Ratio"] <= 1.0)].sort_values(by="diff_sma50")
    if not near_50.empty:
        display_styled_dataframe(near_50, cols_tab3 + ["SMA50"])
    else:
        st.write("조건 만족 종목 없음")
    st.divider()

    st.markdown("### 🔹 20일선 근접 + 거래량 감축")
    near_20 = df[(df["diff_sma20"] <= 3.0) & (df["Volume_Ratio"] <= 1.0)].sort_values(by="diff_sma20")
    if not near_20.empty:
        display_styled_dataframe(near_20, cols_tab3 + ["SMA20"])
    else:
        st.write("조건 만족 종목 없음")
    st.divider()

    st.markdown("### 🔹 9일선 근접 + 거래량 감축")
    near_9 = df[(df["diff_sma9"] <= 3.0) & (df["Volume_Ratio"] <= 1.0)].sort_values(by="diff_sma9")
    if not near_9.empty:
        display_styled_dataframe(near_9, cols_tab3 + ["SMA9"])
    else:
        st.write("조건 만족 종목 없음")

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
    cols_tab4 = ["티커", "섹터", "Yahoo", "SeekingAlpha", "국면분류", "현재가", "Volume_Ratio", "SMA20", "SMA50", "SMA200", "PER_개선", "Forward_PE"]
    display_styled_dataframe(filtered_df, cols_tab4)
