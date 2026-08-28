import streamlit as st
import yfinance as yf
import pandas as pd
import os

# 1. 페이지 설정
st.set_page_config(page_title="맞춤형 & S&P 500 퀀트 스크리너", page_icon="📈", layout="wide")

st.title("📈 커스텀 & S&P 500 퀀트 스크리너 대시보드")
st.caption("대가들의 매매 전략(Minervini, O'Neil, Williams) 기반 맞춤형 분석 시스템")

# 2. 로컬 CSV 파일에서 S&P 500 전체 종목 불러오기
@st.cache_data(ttl=86400)
def get_sp500_tickers():
    csv_file = "sp500_tickers.csv"
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            tickers = df['Symbol'].dropna().str.strip().str.replace('.', '-', regex=False).tolist()
            return tickers
        except Exception:
            pass
    # 파일이 없거나 읽기 실패 시 예외용 기본 리스트
    return ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "TSLA", "AVGO", "LLY"]

# 3. 고속 일괄(Batch) 데이터 수집 및 이평선 계산 함수
@st.cache_data(ttl=3600)
def fetch_and_process_data_fast(tickers):
    if not tickers:
        return pd.DataFrame()

    with st.spinner(f"총 {len(tickers)}개 종목 데이터를 분석 중입니다... (약 10~20초 소요)"):
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

            all_data.append({
                "티커": ticker,
                "현재가": round(price, 2),
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
# 사이드바
# ------------------------------------------------------------------
st.sidebar.header("⚙️ 스크리닝 대상 설정")
mode = st.sidebar.radio(
    "분석할 대상을 선택하세요:",
    ("S&P 500 전체 종목", "직접 티커 입력하기")
)

if mode == "S&P 500 전체 종목":
    target_tickers = get_sp500_tickers()
    st.sidebar.info(f"S&P 500 구성 종목 {len(target_tickers)}개를 전체 분석합니다.")
else:
    custom_input = st.sidebar.text_area(
        "분석할 티커를 쉼표(,)로 구분해 입력하세요:",
        value="TSLA, PLTR, NVDA, AMD, QQQ, SPY, COIN",
        height=120
    )
    target_tickers = [t.strip() for t in custom_input.replace('\n', ',').split(',') if t.strip()]
    st.sidebar.success(f"입력된 {len(target_tickers)}개 종목을 분석합니다.")

# 데이터 수집 실행
df = fetch_and_process_data_fast(target_tickers)

st.success(f"총 {len(df)}개 종목 분석 완료!")
if st.button("🔄 데이터 강제 갱신", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

if df.empty:
    st.warning("분석할 종목 데이터가 없거나 수집 중 오류가 발생했습니다.")
    st.stop()

# ------------------------------------------------------------------
# 탭 구성 (모바일 최적화 세로 1열 배치)
# ------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "🏆 전략 1: 미너비니 정배열", 
    "🎯 전략 2: 오닐 눌림목 반등", 
    "📍 전략 3: 이평선별 근접 종목"
])

# TAB 1: 미너비니 정배열
with tab1:
    st.subheader("전략 1. 미너비니 트렌드 템플릿 (완전 정배열 주도주)")
    st.caption("**조건**: `200일 < 100일 < 50일 < 20일` AND `Forward PER < Trailing PER`")
    
    cond1 = (
        (df["SMA200"] < df["SMA100"]) & 
        (df["SMA100"] < df["SMA50"]) & 
        (df["SMA50"] < df["SMA20"]) & 
        df["PER_개선"]
    )
    res1 = df[cond1][["티커", "현재가", "SMA20", "SMA50", "SMA100", "SMA200", "Trailing_PE", "Forward_PE"]]
    
    if not res1.empty:
        st.dataframe(res1, use_container_width=True)
    else:
        st.info("현재 완전 정배열 조건과 PER 개선을 동시에 만족하는 종목이 없습니다.")

# TAB 2: 오닐 눌림목 반등
with tab2:
    st.subheader("전략 2. 오닐 & 와인스타인 눌림목 반등 타점")
    st.caption("**조건**: `200일 < 100일 < 50일` (장기 우상향) AND `9일선 > 20일선` (단기 반등) AND `Forward PER 개선`")
    
    cond2 = (
        (df["SMA200"] < df["SMA100"]) & 
        (df["SMA100"] < df["SMA50"]) & 
        (df["SMA9"] > df["SMA20"]) & 
        (df["현재가"] > df["SMA9"]) &
        df["PER_개선"]
    )
    res2 = df[cond2][["티커", "현재가", "SMA9", "SMA20", "SMA50", "Trailing_PE", "Forward_PE"]]
    
    if not res2.empty:
        st.dataframe(res2, use_container_width=True)
    else:
        st.info("현재 눌림목 후 단기 반등 조건을 만족하는 종목이 없습니다.")

# TAB 3: 이평선별 근접 종목
with tab3:
    st.subheader("전략 3. 각 이동평균선 근처(±3% 이내) 종목")
    st.caption("주가가 이동평균선에 바짝 붙은 종목을 모바일 화면에 맞춰 순차적으로 보여줍니다.")

    st.markdown("### 🔹 200일선 근접 (장기 지지선)")
    near_200 = df[df["diff_sma200"] <= 3.0].sort_values(by="diff_sma200")
    if not near_200.empty:
        st.dataframe(near_200[["티커", "현재가", "SMA200", "Forward_PE"]], use_container_width=True)
    else:
        st.write("근접 종목 없음")
    st.divider()

    st.markdown("### 🔹 100일선 근접 (중장기 허리선)")
    near_100 = df[df["diff_sma100"] <= 3.0].sort_values(by="diff_sma100")
    if not near_100.empty:
        st.dataframe(near_100[["티커", "현재가", "SMA100", "Forward_PE"]], use_container_width=True)
    else:
        st.write("근접 종목 없음")
    st.divider()

    st.markdown("### 🔹 50일선 근접 (기관 수급선)")
    near_50 = df[df["diff_sma50"] <= 3.0].sort_values(by="diff_sma50")
    if not near_50.empty:
        st.dataframe(near_50[["티커", "현재가", "SMA50", "Forward_PE"]], use_container_width=True)
    else:
        st.write("근접 종목 없음")
    st.divider()

    st.markdown("### 🔹 20일선 근접 (단기 생명선)")
    near_20 = df[df["diff_sma20"] <= 3.0].sort_values(by="diff_sma20")
    if not near_20.empty:
        st.dataframe(near_20[["티커", "현재가", "SMA20", "Forward_PE"]], use_container_width=True)
    else:
        st.write("근접 종목 없음")
    st.divider()

    st.markdown("### 🔹 9일선 근접 (극단기 모멘텀선)")
    near_9 = df[df["diff_sma9"] <= 3.0].sort_values(by="diff_sma9")
    if not near_9.empty:
        st.dataframe(near_9[["티커", "현재가", "SMA9", "Forward_PE"]], use_container_width=True)
    else:
        st.write("근접 종목 없음")
