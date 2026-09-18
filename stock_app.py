import streamlit as st
import yfinance as yf
import pandas as pd
import os

# 1. 페이지 설정
st.set_page_config(page_title="맞춤형 & S&P 500 퀀트 스크리너", page_icon="📈", layout="wide")
st.title("📈 커스텀 & S&P 500 퀀트 스크리너 대시보드")
st.caption("대가들의 매매 전략 + 마법공식 및 대체 퀄리티-밸류(ROE/FCF) 스크리닝")

# 2. 파일 파싱 함수
@st.cache_data(ttl=86400)
def load_tickers_and_sectors_from_file(file_path):
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
                    if line_str.startswith('#'):
                        current_sector = line_str.lstrip('#').strip()
                        continue
                    parts = [p.strip() for p in line_str.split(',')]
                    ticker = parts[0].replace('.', '-').upper()
                    if ticker in ["TICKER", "SYMBOL", "종목코드"]:
                        continue
                    if ticker:
                        tickers.append(ticker)
                        ticker_sector_map[ticker] = current_sector
        except Exception:
            pass
    return tickers, ticker_sector_map

# 3. 데이터 수집 및 대체 지표(ROE, ROA, FCF Yield) 파싱 함수
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
                
                # 차트 이평선 및 수급
                price = float(close.iloc[-1])
                sma200 = float(close.rolling(200).mean().iloc[-1])
                sma100 = float(close.rolling(100).mean().iloc[-1])
                sma50  = float(close.rolling(50).mean().iloc[-1])
                sma20  = float(close.rolling(20).mean().iloc[-1])
                sma9   = float(close.rolling(9).mean().iloc[-1])
                
                curr_vol = float(volume.iloc[-1])
                vol_sma20 = float(volume.rolling(20).mean().iloc[-1])
                vol_sma5  = float(volume.rolling(5).mean().iloc[-1])
                vol_ratio = (curr_vol / vol_sma20) if vol_sma20 > 0 else 0.0
                
                # 최근 5일 수급 유입 검증
                recent_5_close = close.iloc[-6:]
                recent_5_vol = volume.iloc[-5:]
                recent_5_volsma20 = volume.rolling(20).mean().iloc[-5:]
                
                has_vol_spike = False
                max_recent_vol_ratio = 0.0
                max_recent_return = 0.0
                
                for i in range(1, len(recent_5_close)):
                    day_ret = ((recent_5_close.iloc[i] - recent_5_close.iloc[i-1]) / recent_5_close.iloc[i-1]) * 100
                    day_vol_ratio = (recent_5_vol.iloc[i-1] / recent_5_volsma20.iloc[i-1]) if recent_5_volsma20.iloc[i-1] > 0 else 0.0
                    if day_vol_ratio > max_recent_vol_ratio:
                        max_recent_vol_ratio = day_vol_ratio
                        max_recent_return = day_ret
                    if day_vol_ratio >= 2.0 and day_ret >= 3.0:
                        has_vol_spike = True
                
                # 펀더멘털 & 마법공식 대체 지표 수집
                sector = file_sector_map.get(ticker)
                trail_pe, fwd_pe = None, None
                roc, earnings_yield = None, None
                roe, roa, fcf_yield = None, None, None
                
                try:
                    t_obj = yf.Ticker(ticker)
                    info_dict = t_obj.info
                    
                    if not sector or sector == "미분류":
                        sector = info_dict.get('sector', 'N/A')
                        
                    fast_info = t_obj.fast_info
                    trail_pe = getattr(fast_info, 'trailing_pe', None)
                    fwd_pe = getattr(fast_info, 'forward_pe', None)
                    
                    # 1. 원조 마법공식 항목
                    ebit = info_dict.get('ebitda') or info_dict.get('operatingCashflow')
                    total_assets = info_dict.get('totalAssets')
                    ev = info_dict.get('enterpriseValue')
                    
                    if ebit and total_assets and total_assets > 0:
                        roc = (ebit / (total_assets * 0.7)) * 100
                    if ebit and ev and ev > 0:
                        earnings_yield = (ebit / ev) * 100
                        
                    # 2. 확실하게 구해지는 마법공식 대체 지표 항목들
                    roe_val = info_dict.get('returnOnEquity')
                    if roe_val is not None:
                        roe = roe_val * 100
                        
                    roa_val = info_dict.get('returnOnAssets')
                    if roa_val is not None:
                        roa = roa_val * 100
                        
                    free_cf = info_dict.get('freeCashflow')
                    mcap = info_dict.get('marketCap')
                    if free_cf and mcap and mcap > 0:
                        fcf_yield = (free_cf / mcap) * 100
                        
                except Exception:
                    if not sector:
                        sector = "N/A"
                        
                pe_improving = bool(fwd_pe and trail_pe and fwd_pe < trail_pe)
                
                # 5대 국면
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
                
                all_data.append({
                    "티커": ticker,
                    "섹터": sector,
                    "Yahoo": f"https://finance.yahoo.com/quote/{ticker}",
                    "SeekingAlpha": f"https://seekingalpha.com/symbol/{ticker}",
                    "현재가": round(price, 2),
                    "국면분류": phase,
                    "Volume_Ratio": round(vol_ratio, 2),
                    "Vol_5일평균": round(vol_sma5, 0),
                    "Vol_20일평균": round(vol_sma20, 0),
                    "최근5일_최대거래량비율": round(max_recent_vol_ratio, 2),
                    "최근5일_최대상승률": round(max_recent_return, 2),
                    "수급유입_신호": has_vol_spike,
                    "SMA9": round(sma9, 2),
                    "SMA20": round(sma20, 2),
                    "SMA50": round(sma50, 2),
                    "SMA100": round(sma100, 2),
                    "SMA200": round(sma200, 2),
                    "Trailing_PE": round(trail_pe, 2) if trail_pe else None,
                    "Forward_PE": round(fwd_pe, 2) if fwd_pe else None,
                    "PER_개선": pe_improving,
                    "ROC": round(roc, 2) if roc is not None else None,
                    "Earnings_Yield": round(earnings_yield, 2) if earnings_yield is not None else None,
                    "ROE": round(roe, 2) if roe is not None else None,
                    "ROA": round(roa, 2) if roa is not None else None,
                    "FCF_Yield": round(fcf_yield, 2) if fcf_yield is not None else None,
                    "diff_sma9": abs((price - sma9) / sma9) * 100,
                    "diff_sma20": abs((price - sma20) / sma20) * 100,
                    "diff_sma50": abs((price - sma50) / sma50) * 100,
                    "diff_sma100": abs((price - sma100) / sma100) * 100,
                    "diff_sma200": abs((price - sma200) / sma200) * 100,
                })
            except Exception:
                continue
                
        df_res = pd.DataFrame(all_data)
        
        # 1. 원조 마법공식 순위
        if not df_res.empty and "ROC" in df_res.columns and "Earnings_Yield" in df_res.columns:
            valid_mf = df_res.dropna(subset=["ROC", "Earnings_Yield"]).copy()
            if not valid_mf.empty:
                valid_mf["ROC_Rank"] = valid_mf["ROC"].rank(ascending=False)
                valid_mf["EY_Rank"] = valid_mf["Earnings_Yield"].rank(ascending=False)
                valid_mf["마법공식_순위"] = (valid_mf["ROC_Rank"] + valid_mf["EY_Rank"]).rank(ascending=True, method="min").astype(int)
                df_res = df_res.merge(valid_mf[["티커", "마법공식_순위"]], on="티커", how="left")
            else:
                df_res["마법공식_순위"] = None
        else:
            df_res["마법공식_순위"] = None

        # 2. 대체 마법공식 (ROE + FCF Yield) 순위
        if not df_res.empty and "ROE" in df_res.columns and "FCF_Yield" in df_res.columns:
            valid_alt = df_res.dropna(subset=["ROE", "FCF_Yield"]).copy()
            if not valid_alt.empty:
                valid_alt["ROE_Rank"] = valid_alt["ROE"].rank(ascending=False)
                valid_alt["FCF_Rank"] = valid_alt["FCF_Yield"].rank(ascending=False)
                valid_alt["대체마법_순위"] = (valid_alt["ROE_Rank"] + valid_alt["FCF_Rank"]).rank(ascending=True, method="min").astype(int)
                df_res = df_res.merge(valid_alt[["티커", "대체마법_순위"]], on="티커", how="left")
            else:
                df_res["대체마법_순위"] = None
        else:
            df_res["대체마법_순위"] = None

        return df_res

# ------------------------------------------------------------------
# 공통 테이블 출력 함수
# ------------------------------------------------------------------
def display_styled_dataframe(df_to_show, columns_to_display):
    column_config = {
        "Yahoo": st.column_config.LinkColumn("Yahoo", display_text="📈 야후", help="야후 파이낸스로 이동"),
        "SeekingAlpha": st.column_config.LinkColumn("SeekingAlpha", display_text="📰 시킹알파", help="시킹알파로 이동"),
        "Volume_Ratio": st.column_config.NumberColumn("당일 거래량 비율", format="%.2f"),
        "최근5일_최대거래량비율": st.column_config.NumberColumn("최근5일 최대거래량비율", format="%.2f"),
        "최근5일_최대상승률": st.column_config.NumberColumn("최근5일 최대상승률 (%)", format="%.2f%%"),
        "ROC": st.column_config.NumberColumn("ROC (%)", format="%.2f%%"),
        "Earnings_Yield": st.column_config.NumberColumn("이익수익률 (%)", format="%.2f%%"),
        "ROE": st.column_config.NumberColumn("ROE (%)", help="자기자본이익률", format="%.2f%%"),
        "ROA": st.column_config.NumberColumn("ROA (%)", help="총자산이익률", format="%.2f%%"),
        "FCF_Yield": st.column_config.NumberColumn("FCF Yield (%)", help="시가총액 대비 잉여현금흐름 비율", format="%.2f%%")
    }
    st.dataframe(df_to_show[columns_to_display], column_config=column_config, use_container_width=True)

# ------------------------------------------------------------------
# 사이드바 설정
# ------------------------------------------------------------------
st.sidebar.header("⚙️ 스크리닝 대상 설정")
portfolio_path = "portfolio.csv"
etf_path = "ETF.csv"
has_portfolio = os.path.exists(portfolio_path)
has_etf = os.path.exists(etf_path)

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
    st.sidebar.info(f"S&P 500 구성 종목 {len(target_tickers)}개를 분석합니다.")
elif mode == "📁 직접 CSV 파일 업로드":
    uploaded_file = st.sidebar.file_uploader("티커가 담긴 CSV 파일을 올려주세요", type=["csv"])
    if uploaded_file is not None:
        try:
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
    custom_input = st.sidebar.text_area("티커를 입력하세요:", value="# Tech\nNVDA, AMD, AAPL, MSFT", height=100)
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

if target_tickers:
    df = fetch_and_process_data_fast(target_tickers, file_sector_map)
else:
    df = pd.DataFrame()

if not df.empty:
    st.success(f"총 {len(df)}개 종목 분석 완료!")
    if st.button("🔄 데이터 강제 갱신", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
else:
    st.stop()

# ------------------------------------------------------------------
# 탭 구성
# ------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏆 전략 1: 미너비니 정배열", 
    "🎯 전략 2: 오닐 반등", 
    "📍 전략 3: 이평선 근접", 
    "🧙‍♂️ 전략 4: 마법공식 (원조 vs 대체)",
    "📊 탭 5: 시장 국면 종합"
])

with tab1:
    st.subheader("전략 1. 미너비니 트렌드 템플릿")
    res1 = df[(df["국면분류"] == "🟢 [그룹 1] 주도주 정배열") & (df["Vol_5일평균"] > df["Vol_20일평균"])]
    cols1 = ["티커", "섹터", "Yahoo", "SeekingAlpha", "현재가", "국면분류", "Volume_Ratio", "SMA20", "SMA50", "SMA200", "Forward_PE"]
    display_styled_dataframe(res1, cols1) if not res1.empty else st.info("조건 만족 종목 없음")

with tab2:
    st.subheader("전략 2. 오닐 눌림목 반등")
    res2 = df[(df["국면분류"] == "🎯 [그룹 2] 눌림목 반등") & (df["Volume_Ratio"] >= 1.2)]
    cols2 = ["티커", "섹터", "Yahoo", "SeekingAlpha", "현재가", "국면분류", "Volume_Ratio", "SMA9", "SMA20", "Forward_PE"]
    display_styled_dataframe(res2, cols2) if not res2.empty else st.info("조건 만족 종목 없음")

with tab3:
    st.subheader("전략 3. 각 이동평균선 근처(±3%) 수급 분석")
    vol_filter_mode = st.radio("거래량 옵션:", ["📉 거래량 소진 (Dry-up)", "🚀 수급 유입 (Volume Spike)"], horizontal=True)
    
    def get_filtered_df(df_source, sma_col, diff_col):
        if "소진" in vol_filter_mode:
            filtered = df_source[(df_source[diff_col] <= 3.0) & (df_source["Volume_Ratio"] <= 1.0)].sort_values(by=diff_col)
            cols = ["티커", "섹터", "Yahoo", "현재가", "Volume_Ratio", "국면분류", sma_col]
        else:
            filtered = df_source[(df_source[diff_col] <= 3.0) & (df_source["수급유입_신호"] == True)].sort_values(by="최근5일_최대거래량비율", ascending=False)
            cols = ["티커", "섹터", "Yahoo", "현재가", "최근5일_최대거래량비율", "최근5일_최대상승률", "국면분류", sma_col]
        return filtered, cols

    st.markdown("### 🔹 200일선 근접")
    d, c = get_filtered_df(df, "SMA200", "diff_sma200")
    display_styled_dataframe(d, c) if not d.empty else st.write("조건 만족 종목 없음")

with tab4:
    st.subheader("전략 4. 퀀트 마법공식 (원조 vs 대체 퀄리티-밸류)")
    
    view_mode = st.radio("조회할 방식을 선택하세요:", ["✨ 대체 마법공식 (ROE + FCF Yield) - 데이터 완성도 높은 추천!", "🧙‍♂️ 원조 마법공식 (ROC + EBIT/EV)"], horizontal=True)
    
    exclude_fin_util = st.checkbox("금융 및 유틸리티 섹터 제외", value=True)
    
    if "대체" in view_mode:
        st.caption("**대체 원리**: 우수한 주주자본 수익성(`ROE`) + 100% 현금 흐름 밸류에이션(`FCF Yield`)의 종합 순위")
        if "대체마법_순위" in df.columns and df["대체마법_순위"].notna().any():
            df_alt = df.dropna(subset=["대체마법_순위"]).sort_values(by="대체마법_순위")
            if exclude_fin_util:
                df_alt = df_alt[~df_alt["섹터"].astype(str).str.contains("Financial|Utility", case=False, na=False)]
            cols_alt = ["대체마법_순위", "티커", "섹터", "ROE", "ROA", "FCF_Yield", "현재가", "Forward_PE", "국면분류", "Yahoo"]
            display_styled_dataframe(df_alt, cols_alt)
        else:
            st.info("대체 지표를 계산할 재무 데이터가 부족합니다.")
    else:
        st.caption("**원조 원리**: 자본수익률(`ROC`) + 이익수익률(`Earnings Yield`)의 종합 순위")
        if "마법공식_순위" in df.columns and df["마법공식_순위"].notna().any():
            df_mf = df.dropna(subset=["마법공식_순위"]).sort_values(by="마법공식_순위")
            if exclude_fin_util:
                df_mf = df_mf[~df_mf["섹터"].astype(str).str.contains("Financial|Utility", case=False, na=False)]
            cols_mf = ["마법공식_순위", "티커", "섹터", "ROC", "Earnings_Yield", "현재가", "Forward_PE", "국면분류", "Yahoo"]
            display_styled_dataframe(df_mf, cols_mf)
        else:
            st.info("원조 마법공식 데이터를 구하지 못했습니다.")

with tab5:
    st.subheader("📊 시장 국면 종합 분석")
    counts = df["국면분류"].value_counts()
    st.write(counts)
    display_styled_dataframe(df, ["티커", "섹터", "Yahoo", "국면분류", "현재가", "Volume_Ratio", "Forward_PE"])
