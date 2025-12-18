import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Environmental Policy Impact Monitor",
    layout="wide"
)

st.title(" Environmental Policy Impact Monitor")

# =========================================================
# TABS
# =========================================================
tab1, tab2 = st.tabs([
    " Emission Impact Analysis",
    " Environmental Policy Extractor"
])

# =========================================================
# HELPER: CLIMATE POLICY DATABASE SCRAPER
# =========================================================
@st.cache_data(ttl=86400)
def extract_policies_cpd(max_pages=60):
    all_dfs = []

    for page in range(max_pages):
        url = f"https://climatepolicydatabase.org/index.php?title=Policies&offset={page*50}"
        try:
            df = pd.read_html(url)[0]
            all_dfs.append(df)
        except Exception:
            break

    if not all_dfs:
        return pd.DataFrame()

    cpd_df = pd.concat(all_dfs, ignore_index=True)
    cpd_df.columns = [c.strip() for c in cpd_df.columns]

    # Detect year column robustly
    year_col = None
    for col in cpd_df.columns:
        if any(k in col.lower() for k in ["year", "start", "date", "adopt"]):
            year_col = col
            break

    if year_col is None:
        return pd.DataFrame()

    cpd_df[year_col] = pd.to_numeric(
        cpd_df[year_col].astype(str).str[:4],
        errors="coerce"
    )

    return cpd_df.rename(columns={
        year_col: "implementation_year",
        "Policy": "policy_name"
    })


# =========================================================
# TAB 1 — EMISSION IMPACT ANALYSIS
# =========================================================
with tab1:

    @st.cache_data
    def load_emission_data():
        return pd.read_csv("data/climate_data.csv")

    df = load_emission_data()
    df.columns = [c.replace("â‚‚", "2") for c in df.columns]
    year_cols = [c for c in df.columns if c.isdigit()]

    st.sidebar.header("Controls")

    country = st.sidebar.selectbox(
        "Select Country",
        sorted(df["Country"].unique())
    )

    sector = st.sidebar.selectbox(
        "Select Sector",
        sorted(df[df["Country"] == country]["Sector"].unique())
    )

    policy_year = st.sidebar.slider(
        "Policy Implementation Year",
        min_value=int(min(year_cols)),
        max_value=int(max(year_cols)),
        value=2015
    )

    country_df = df[df["Country"] == country]

    long_df = country_df.melt(
        id_vars=["ISO", "Country", "Sector", "Gas", "Unit"],
        value_vars=year_cols,
        var_name="Year",
        value_name="Emissions"
    )

    long_df["Year"] = long_df["Year"].astype(int)
    long_df["Emissions"] = pd.to_numeric(long_df["Emissions"], errors="coerce")
    long_df.dropna(inplace=True)

    plot_df = long_df[long_df["Sector"] == sector].sort_values("Year")

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(plot_df["Year"], plot_df["Emissions"], marker="o", label="Emissions")

    # Selected policy year
    ax.axvline(policy_year, color="red", linestyle="--", linewidth=2, label="Selected Policy Year")

    # =====================================================
    # POLICY OVERLAY (CPD)
    # =====================================================
    policy_df = extract_policies_cpd(60)

    if not policy_df.empty:
        policy_year_df = policy_df[policy_df["implementation_year"] == policy_year]

        # Try to filter by country if column exists
        if "Country" in policy_year_df.columns:
            policy_year_df = policy_year_df[
                policy_year_df["Country"].str.contains(country, case=False, na=False)
            ]

        policy_year_df = policy_year_df.head(5)

        for _, row in policy_year_df.iterrows():
            ax.axvline(
                row["implementation_year"],
                color="green",
                linestyle=":",
                alpha=0.6
            )
            ax.text(
                row["implementation_year"] + 0.1,
                ax.get_ylim()[1] * 0.95,
                row["policy_name"][:35] + "...",
                rotation=90,
                fontsize=8,
                color="green"
            )

    ax.set_title(f"{country} – {sector} Emissions Over Time")
    ax.set_xlabel("Year")
    ax.set_ylabel("Emissions")
    ax.legend()

    st.pyplot(fig)

    # =====================================================
    # IMPACT SUMMARY
    # =====================================================
    before = plot_df[plot_df["Year"] < policy_year]["Emissions"].mean()
    after = plot_df[plot_df["Year"] >= policy_year]["Emissions"].mean()

    st.subheader("📊 Policy Impact Summary")
    c1, c2, c3 = st.columns(3)

    c1.metric("Avg Before Policy", round(before, 2))
    c2.metric("Avg After Policy", round(after, 2))

    if before > 0:
        c3.metric("Change (%)", round(((after - before) / before) * 100, 2))
    else:
        c3.metric("Change (%)", "N/A")

    if not policy_df.empty and not policy_year_df.empty:
        st.markdown("### 📜 Policies Implemented This Year")
        st.dataframe(
            policy_year_df[["policy_name", "implementation_year"]],
            use_container_width=True
        )

def extract_environment_policies(year, max_pages=3):
    
    base_url = "https://www.federalregister.gov/api/v1/documents.json"
    all_records = []

    for page in range(1, max_pages + 1):
        params = {
            "conditions[term]": "environment climate emissions carbon",
            "conditions[publication_date][year]": year,
            "order": "newest",
            "per_page": 100,
            "page": page
        }

        try:
            response = requests.get(base_url, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
        except Exception:
            break

        results = data.get("results", [])
        if not results:
            break

        for item in results:
            agencies = item.get("agencies", [])
            agency_names = [
                agency["name"] for agency in agencies
                if isinstance(agency, dict) and "name" in agency
            ]

            all_records.append({
                "policy_name": item.get("title"),
                "policy_type": item.get("type"),
                "implementation_year": year,
                "agency": ", ".join(agency_names) if agency_names else "N/A",
                "source": "US Federal Register",
                "source_url": item.get("html_url")
            })

    return pd.DataFrame(all_records)
# =========================================================
# TAB 2 — POLICY DATASET EXTRACTOR
# =========================================================
with tab2:
    st.subheader("📜 Environmental Policy Dataset Extractor")

    selected_year = st.selectbox(
        "Select Policy Year",
        list(range(1995, 2026))[::-1]
    )

    if st.button("🔍 Extract Policies"):
        with st.spinner("Fetching policies from Federal Register..."):
            policy_df = extract_environment_policies(selected_year)

        if policy_df.empty:
            st.warning(f"No policies found for year {selected_year}.")
        else:
            st.success(f"Found {len(policy_df)} policies for {selected_year}")
            st.dataframe(policy_df, use_container_width=True)

            st.download_button(
                "⬇ Download Policy Dataset (CSV)",
                policy_df.to_csv(index=False).encode("utf-8"),
                file_name=f"environmental_policies_{selected_year}.csv",
                mime="text/csv"
            )
