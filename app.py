import streamlit as st
import yfinance as yf
import pandas as pd

# 1. 페이지 기본 설정 및 디자인
st.set_page_config(page_title="S&P 500 퀀트 스크리너", page_icon="📈", layout="wide")

st.title("📈 S&P 500 퀀트 스크리너 대시보드")
st.caption("조건: 200일 이동평균선 ±5% 이내 근접 & Forward PER 개선 종목")

# 2. 분석할 S&P 500 주요 종목 리스트
TICKERS = ["MSFT", "GOOGL", "AAPL", "AMZN", "NVDA", "V", "AMAT", "LLY", "JNJ", "PG", "COST", "HD"]

@st.cache_data(ttl=3600)  # 1시간 동안 데이터를 캐싱하여 속도 최적화
def run_screener():
    results = []
    for ticker in TICKERS:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            if len(hist) < 200:
                continue

            # 200일선 및 이격도 계산
            hist['SMA200'] = hist['Close'].rolling(window=200).mean()
            current_price = float(hist['Close'].iloc[-1])
            sma200 = float(hist['SMA200'].iloc[-1])
            diff_pct = ((current_price - sma200) / sma200) * 100

            # PER 데이터 가져오기
            info = stock.info
            trail_pe = info.get('trailingPE')
            fwd_pe = info.get('forwardPE')
            name = info.get('shortName', ticker)

            # 조건 판별: 200일선 ±5% 이내 AND Forward PER < Trailing PER
            if abs(diff_pct) <= 5.0 and (fwd_pe and trail_pe and fwd_pe < trail_pe):
                results.append({
                    "티커": ticker,
                    "종목명": name,
                    "현재가 ($)": round(current_price, 2),
                    "200일선 ($)": round(sma200, 2),
                    "이격도 (%)": round(diff_pct, 2),
                    "Trailing PE": round(trail_pe, 2),
                    "Forward PE": round(fwd_pe, 2)
                })
        except Exception as e:
            continue
    return pd.DataFrame(results)

# 3. 화면 UI 및 데이터 표시
if st.button("🔄 스크리닝 실행 / 갱신"):
    st.cache_data.clear()

with st.spinner("주가 및 실적 데이터를 스크리닝 중입니다..."):
    df = run_screener()

if not df.empty:
    col1, col2 = st.columns(2)
    col1.metric("검색된 종목 수", f"{len(df)} 개")
    
    # 결과 데이터프레임 표 출력
    st.dataframe(
        df.style.highlight_min(axis=0, color="#d4edda", subset=["Forward PE"]),
        use_container_width=True
    )
else:
    st.info("현재 조건을 만족하는 종목이 없습니다.")