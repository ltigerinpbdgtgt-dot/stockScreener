import streamlit as st
import yfinance as yf
import pandas as pd

# 1. 페이지 설정
st.set_page_config(page_title="S&P 500 전체 퀀트 스크리너", page_icon="📈", layout="wide")

st.title("📈 S&P 500 전체 종목 퀀트 & 다중 이평선 대시보드")
st.caption("위키피디아 실시간 S&P 500 전체 종목 연동 | 대가들의 매매 전략 기반 시스템")

# 2. S&P 500 전체 500개 종목 티커 자동 수집 함수
@st.cache_data(ttl=86400) # S&P 500 구성 종목 리스트는 하루(24시간)에 한 번만 갱신
def get_sp500_tickers():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        df = tables[0]
        # yfinance 호환성을 위해 티커 내 점(.)을 하이픈(-)으로 변경 (예: BRK.B -> BRK-B)
        tickers = df['Symbol'].str.replace('.', '-', regex=False).tolist()
        return tickers
    except Exception as e:
        # 비상용 기본 티커 리스트
        return ["MSFT", "GOOGL", "AAPL", "AMZN", "NVDA", "V", "AMAT", "LLY", "JNJ", "PG"]

@st.cache_data(ttl=3600) # 주가 데이터는 1시간 캐싱
def fetch_and_process_data(tickers):
    all_data = []
    
    # 작업 진행 상황을 보여주는 진행바(Progress Bar)
    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(tickers)

    for idx, ticker in enumerate(tickers):
        # 진행 상태 업데이트
        progress = (idx + 1) / total
        progress_bar.progress(progress)
        status_text.text(f"스크리닝 중... ({idx+1}/{total}): {ticker}")

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            
            if len(hist) < 200:
                continue

            # 5가지 이동평균선 계산
            hist['SMA200'] = hist['Close'].rolling(window=200).mean()
            hist['SMA100'] = hist['Close'].rolling(window=100).mean()
            hist['SMA50']  = hist['Close'].rolling(window=50).mean()
            hist['SMA20']  = hist['Close'].rolling(window=20).mean()
            hist['SMA9']   = hist['Close'].rolling(window=9).mean()

            price = float(hist['Close'].iloc[-1])
            sma200 = float(hist['SMA200'].iloc[-1])
            sma100 = float(hist['SMA100'].iloc[-1])
            sma50  = float(hist['SMA50'].iloc[-1])
            sma20  = float(hist['SMA20'].iloc[-1])
            sma9   = float(hist['SMA9'].iloc[-1])

            # 펀더멘털 PER 정보
            info = stock.info
            trail_pe = info.get('trailingPE')
            fwd_pe = info.get('forwardPE')
            name = info.get('shortName', ticker)

            # PER 개선 여부
            pe_improving = bool(fwd_pe and trail_pe and fwd_pe < trail_pe)

            all_data.append({
                "티커": ticker,
                "종목명": name,
                "현재가": round(price, 2),
                "SMA9": round(sma9, 2),
                "SMA20": round(sma20, 2),
                "SMA50": round(sma50, 2),
                "SMA100": round(sma100, 2),
                "SMA200": round(sma200, 2),
                "Trailing_PE": round(trail_pe, 2) if trail_pe else None,
                "Forward_PE": round(fwd_pe, 2) if fwd_pe else None,
                "PER_개선": pe_improving,
                # 이격도 (%) 계산
                "diff_sma9": abs((price - sma9) / sma9) * 100,
                "diff_sma20": abs((price - sma20) / sma20) * 100,
                "diff_sma50": abs((price - sma50) / sma50) * 100,
                "diff_sma100": abs((price - sma100) / sma100) * 100,
                "diff_sma200": abs((price - sma200) / sma200) * 100,
            })
        except Exception:
            continue

    # 작업 완료 후 진행바 제거
    progress_bar.empty()
    status_text.empty()

    return pd.DataFrame(all_data)

# S&P 500 전체 종목 가져오기
tickers = get_sp500_tickers()

# 데이터 로딩
df = fetch_and_process_data(tickers)

col_top1, col_top2 = st.columns([8, 2])
with col_top1:
    st.success(f"총 {len(df)}개 S&P 500 종목 데이터 수집 및 분석 완료!")
with col_top2:
    if st.button("🔄 전체 데이터 강제 갱신"):
        st.cache_data.clear()
        st.rerun()

# 탭 구성
tab1, tab2, tab3 = st.tabs([
    "🏆 전략 1: 미너비니 트렌드 템플릿", 
    "🎯 전략 2: 오닐 눌림목 반등 타점", 
    "📍 전략 3: 이평선별 근접 종목"
])

# ------------------------------------------------------------------
# TAB 1: 미너비니 트렌드 템플릿
# ------------------------------------------------------------------
with tab1:
    st.subheader("전략 1. 미너비니 트렌드 템플릿 (완전 정배열 주도주)")
    st.markdown("**조건**: `200일 < 100일 < 50일 < 20일` AND `Forward PER < Trailing PER`")
    
    cond1 = (
        (df["SMA200"] < df["SMA100"]) & 
        (df["SMA100"] < df["SMA50"]) & 
        (df["SMA50"] < df["SMA20"]) & 
        df["PER_개선"]
    )
    res1 = df[cond1][["티커", "종목명", "현재가", "SMA20", "SMA50", "SMA100", "SMA200", "Trailing_PE", "Forward_PE"]]
    
    if not res1.empty:
        st.dataframe(res1, use_container_width=True)
    else:
        st.info("현재 완전 정배열 조건과 PER 개선을 동시에 만족하는 종목이 없습니다.")

# ------------------------------------------------------------------
# TAB 2: 오닐/와인스타인 눌림목 반등
# ------------------------------------------------------------------
with tab2:
    st.subheader("전략 2. 오닐 & 와인스타인 눌림목 반등 타점")
    st.markdown("**조건**: `200일 < 100일 < 50일` (장기 우상향) AND `9일선 > 20일선` (단기 반등) AND `Forward PER 개선`")
    
    cond2 = (
        (df["SMA200"] < df["SMA100"]) & 
        (df["SMA100"] < df["SMA50"]) & 
        (df["SMA9"] > df["SMA20"]) & 
        (df["현재가"] > df["SMA9"]) &
        df["PER_개선"]
    )
    res2 = df[cond2][["티커", "종목명", "현재가", "SMA9", "SMA20", "SMA50", "Trailing_PE", "Forward_PE"]]
    
    if not res2.empty:
        st.dataframe(res2, use_container_width=True)
    else:
        st.info("현재 눌림목 후 단기 반등 조건을 만족하는 종목이 없습니다.")

# ------------------------------------------------------------------
# TAB 3: 각 이동평균선별 근처(±3% 이내)에 있는 종목 나열
# ------------------------------------------------------------------
with tab3:
    st.subheader("전략 3. 각 이동평균선 근처(±3% 이내) 종목 스크리닝")
    st.caption("현재 주가가 각 이동평균선 부근에 바짝 붙어있는 종목을 가까운 순서대로 나열합니다.")

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🔹 200일선 근접 (장기 지지선)")
        near_200 = df[df["diff_sma200"] <= 3.0].sort_values(by="diff_sma200")
        if not near_200.empty:
            st.dataframe(near_200[["티커", "현재가", "SMA200", "Forward_PE"]], use_container_width=True)
        else:
            st.write("근접 종목 없음")

    with col2:
        st.markdown("### 🔹 100일선 근접 (중장기 허리선)")
        near_100 = df[df["diff_sma100"] <= 3.0].sort_values(by="diff_sma100")
        if not near_100.empty:
            st.dataframe(near_100[["티커", "현재가", "SMA100", "Forward_PE"]], use_container_width=True)
        else:
            st.write("근접 종목 없음")

    with col3:
        st.markdown("### 🔹 50일선 근접 (기관 수급선)")
        near_50 = df[df["diff_sma50"] <= 3.0].sort_values(by="diff_sma50")
        if not near_50.empty:
            st.dataframe(near_50[["티커", "현재가", "SMA50", "Forward_PE"]], use_container_width=True)
        else:
            st.write("근접 종목 없음")

    st.divider()
    col4, col5 = st.columns(2)

    with col4:
        st.markdown("### 🔹 20일선 근접 (단기 생명선)")
        near_20 = df[df["diff_sma20"] <= 3.0].sort_values(by="diff_sma20")
        if not near_20.empty:
            st.dataframe(near_20[["티커", "현재가", "SMA20", "Forward_PE"]], use_container_width=True)
        else:
            st.write("근접 종목 없음")

    with col5:
        st.markdown("### 🔹 9일선 근접 (극단기 모멘텀선)")
        near_9 = df[df["diff_sma9"] <= 3.0].sort_values(by="diff_sma9")
        if not near_9.empty:
            st.dataframe(near_9[["티커", "현재가", "SMA9", "Forward_PE"]], use_container_width=True)
        else:
            st.write("근접 종목 없음")
