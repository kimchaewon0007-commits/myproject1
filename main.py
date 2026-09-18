import io
import gzip
import requests
import pandas as pd
import plotly.express as px
import streamlit as st

# ==========================================
# 1. 페이지 기본 설정
# ==========================================
st.set_page_config(
    page_title="전국 고령화 지도 대시보드", page_icon="🗺️", layout="wide"
)

st.title("🗺️ 대한민국 시군구별 고령화율 지도 (최신 연도 기준)")
st.markdown(
    "전국 읍·면·동 인구 데이터를 바탕으로 **시군구별 65세 이상 인구 비율**을 계산하여 5단계 구간으로 시각화한 대시보드입니다."
)


# ==========================================
# 2. 데이터 로드 및 캐싱 (성능 최적화)
# ==========================================
@st.cache_data
def load_population_data():
    """인구 데이터를 다운로드하고 압축을 해제하여 데이터프레임으로 반환합니다."""
    url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    res = requests.get(url)
    # gzip 압축 해제 (코드 열은 '0'이 유실되지 않도록 str로 읽기)
    with gzip.open(io.BytesIO(res.content), "rt", encoding="utf-8") as f:
        df = pd.read_csv(f, dtype={"코드": str})
    return df


@st.cache_data
def load_geojson_data():
    """시군구 경계 GeoJSON 데이터를 다운로드합니다."""
    url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    res = requests.get(url)
    return res.json()


# 데이터 로딩 상태 표시
with st.spinner("데이터를 불러오는 중입니다. 잠시만 기다려 주세요..."):
    df_pop = load_population_data()
    geojson_sigungu = load_geojson_data()


# ==========================================
# 3. 데이터 전처리 및 고령화율 계산
# ==========================================
# 1) 가장 최신 연도 추출
latest_year = df_pop["연도"].max()
df_latest = df_pop[df_pop["연도"] == latest_year].copy()

# 2) 코드 앞 5자리를 추출하여 시군구 단위 키 생성 ('코드' 열을 5자리 문자열로 보정)
df_latest["코드"] = df_latest["코드"].astype(str).str.zfill(10)
df_latest["sigungu_code"] = df_latest["sigungu_code"] = df_latest[
    "코드"
].str.slice(0, 5)


# 3) 65세 이상 인구 및 전체 인구 합산 컬럼 찾기
# '계_65세'부터 '계_100세 이상'까지의 컬럼들을 골라냄
age_cols = [
    col
    for col in df_latest.columns
    if col.startswith("계_")
    and col not in ["계_0세", "계_1세", "계_2세", "계_3세", "계_4세", "계_5세"]
]


# 65세 이상에 해당하는 나이 추출 함수
def is_over_65(col_name):
    if "100세 이상" in col_name:
        return True
    # 예: '계_65세' -> 숫자 65 추출
    parts = col_name.replace("계_", "").replace("세", "").strip()
    if parts.isdigit():
        return int(parts) >= 65
    return False


elderly_cols = [col for col in age_cols if is_over_65(col)]
all_age_cols = age_cols  # 전체 연령 합산을 위해 모든 계_ 컬럼 사용


# 4) 시군구별로 그룹화하여 총인구 및 65세 이상 인구 계산
# 읍·면·동 단위 데이터를 시군구(sigungu_code) 단위로 합산
df_latest["total_population"] = df_latest[all_age_cols].sum(axis=1)
df_latest["elderly_population"] = df_latest[elderly_cols].sum(axis=1)

sigungu_agg = (
    df_latest.groupby("sigungu_code")
    .agg(
        {
            "시도": "first",
            "시군구": "first",
            "total_population": "sum",
            "elderly_population": "sum",
        }
    )
    .reset_index()
)

# 5) 고령화율(%) 계산
sigungu_agg["고령화율"] = (
    sigungu_agg["elderly_population"] / sigungu_agg["total_population"]
) * 100


# ==========================================
# 4. 5단계 구간화(Binning) 처리
# ==========================================
# 요구된 구간 경계값: 19%, 23%, 28%, 38%
# 범주형 구간 레이블 설정
bins = [-float("inf"), 19.0, 23.0, 28.0, 38.0, float("inf")]
labels = ["19% 미만", "19% ~ 23%", "23% ~ 28%", "28% ~ 38%", "38% 이상"]

sigungu_agg["고령화_구간"] = pd.cut(
    sigungu_agg["고령화율"], bins=bins, labels=labels, right=False
)

# 지도 시각화를 위한 소수점 정리
sigungu_agg["고령화율_표시"] = sigungu_agg["고령화율"].round(2)


# ==========================================
# 5. Plotly Choropleth 지도 그리기
# ==========================================
st.subheader(f"📊 {latest_year}년 전국 시군구 고령화율 단계구분도")

# 지도 색상 팔레트 (연한 색 -> 진한 색)
color_sequence = ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"]

fig = px.choropleth(
    sigungu_agg,
    geojson=geojson_sigungu,
    locations="sigungu_code",
    featureidkey="properties.코드",
    color="고령화_구간",
    category_orders={"고령화_구간": labels},
    color_discrete_sequence=color_sequence,
    hover_name="시군구",
    hover_data={
        "시도": True,
        "고령화율_표시": True,
        "sigungu_code": False,
        "고령화_구간": False,
    },
    labels={"고령화_구간": "고령화율 구간", "고령화율_표시": "고령화율(%)"},
)

# 지도 레이아웃 설정 (배경 지도 타일 없이 경계선만 표시)
fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin={"r": 0, "t": 0, "l": 0, "b": 0},
    legend_title_text="<b>고령화율 구간</b>",
    height=650,
)

# 지도 출력
st.plotly_chart(fig, use_container_width=True)


# ==========================================
# 6. 상하위 10개 지역 표 출력
# ==========================================
st.markdown("---")
st.subheader("🏆 시군구 고령화율 순위 (상위 10개 vs 하위 10개)")

col1, col2 = st.columns(2)

# 정렬
df_sorted = sigungu_agg.sort_values(by="고령화율", ascending=False).reset_index(
    drop=True
)

with col1:
    st.markdown("#### 🔴 고령화율 높은 지역 TOP 10")
    top_10 = df_sorted.head(10)[
        ["시도", "시군구", "고령화율_표시", "고령화_구간"]
    ].copy()
    top_10.columns = ["시도", "시군구", "고령화율(%)", "구분"]
    top_10.index = range(1, 11)
    st.dataframe(top_10, use_container_width=True)

with col2:
    st.markdown("#### 🔵 고령화율 낮은 지역 TOP 10")
    # 하위 10개를 위에서부터 보이게 정렬
    bottom_10 = (
        df_sorted.tail(10)
        .sort_values(by="고령화율", ascending=True)[
            ["시도", "시군구", "고령화율_표시", "고령화_구간"]
        ]
        .copy()
    )
    bottom_10.columns = ["시도", "시군구", "고령화율(%)", "구분"]
    bottom_10.index = range(1, 11)
    st.dataframe(bottom_10, use_container_width=True)

# 푸터 정보
st.markdown("---")
st.caption("✨ Developed with Streamlit & Plotly | Data Source: 행정안전부 인구 데이터")
