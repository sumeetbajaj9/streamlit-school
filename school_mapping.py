import json
import logging
import os
import uuid
import time
import pandas as pd
import requests
import streamlit as st

API_URL = "https://api.cert.hmhco.com/idm-staging-processor/api/v1/schoolMappings"

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "school_mapping.log")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)
VALID_PLATFORMS = ["ED"]

REQUIRED_CSV_COLUMNS = {"sourcedId", "name", "orgRefId"}
OPTIONAL_CSV_COLUMNS = {"nweaSchoolBid", "platforms"}

st.set_page_config(page_title="School Mapping Creator", page_icon="🏫", layout="centered")

st.markdown(
    """
    <style>
    /* Force pure-black backgrounds everywhere */
    html, body,
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stSidebar"],
    section[data-testid="stSidebar"],
    [data-testid="stHeader"] {
      background-color: #000000 !important;
      color: #ffffff !important;
    }

    /* Some Streamlit versions use these wrappers */
    [data-testid="stAppViewContainer"] > .main,
    [data-testid="stAppViewContainer"] > .main > div {
      background-color: #000000 !important;
    }

    .block-container { max-width: 780px; padding-top: 2rem; background-color: #000000 !important; }
    div[data-testid="stStatusWidget"] { display: none; }
    .stTabs [data-baseweb="tab-list"] { gap: 2rem; }
    /* Dark inputs and cards */
    div[data-testid="stExpander"],
    div[data-baseweb="select"] > div,
    [data-baseweb="input"] {
      background-color: #111111 !important;
      color: #ffffff !important;
    }
    /* Logo container */
    div[data-testid="stImage"] img { border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Logo and title header
logo_path = "images.png"
header_col1, header_col2 = st.columns([1, 5])
with header_col1:
    try:
        st.image(logo_path, use_container_width=True)
    except FileNotFoundError:
        pass
with header_col2:
    st.title("School Mapping Creator")
    st.caption("Create and manage school mappings")
st.divider()

if "history" not in st.session_state:
    st.session_state.history = []


# ── helpers ──────────────────────────────────────────────────────────────────

def build_headers(token, correlation_id):
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "authorization": f"SIF_HMACSHA256 {token.strip()}",
        "content-type": "application/json",
        "correlationid": correlation_id,
        "origin": "https://cert.hmhco.com",
        "referer": "https://cert.hmhco.com/",
        "timezoneoffset": "5.5",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/144.0.0.0 Safari/537.36"
        ),
    }


def send_mapping(token, payload):
    cid = f"{uuid.uuid4()}-{uuid.uuid4().hex[:12]}"
    headers = build_headers(token, cid)
    log.info("POST %s | correlation_id=%s | payload=%s", API_URL, cid, json.dumps(payload))
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    log.info("Response status=%s | correlation_id=%s | body=%s", resp.status_code, cid, resp.text[:500] if resp.text else "")
    return resp, cid


def parse_platforms(value):
    """Turn a string like 'HRW,TC,ED' or a list into a Python list."""
    if isinstance(value, list):
        return value
    if pd.isna(value) or str(value).strip() == "":
        return VALID_PLATFORMS[:]
    return [p.strip().upper() for p in str(value).split(",") if p.strip()]


# ── auth (shared) ───────────────────────────────────────────────────────────

st.subheader("Authentication")
auth_token = st.text_area(
    "Authorization Token",
    placeholder="Paste the SIF_HMACSHA256 token value here…",
    height=80,
    help="The base-64 encoded token (without the 'SIF_HMACSHA256 ' prefix).",
    key="auth_token",
)

st.divider()

tab_single, tab_csv = st.tabs(["Single Entry", "CSV Bulk Upload"])

# ── Tab 1: Single entry ─────────────────────────────────────────────────────

with tab_single:
    with st.form("single_form"):
        col1, col2 = st.columns(2)
        with col1:
            sourced_id = st.text_input("Sourced ID", placeholder="e.g. 69846862a773fdd0a9d5fcb5")
        with col2:
            name = st.text_input("School Name", placeholder="e.g. Facepink")

        col3, col4 = st.columns(2)
        with col3:
            org_ref_id = st.text_input("Org Ref ID", placeholder="e.g. 33b4aa75-9dba-386a-…")
        with col4:
            nwea_school_bid = st.text_input("NWEA School BID", value="SKIP")

        platforms = st.multiselect("Platforms", options=VALID_PLATFORMS, default=VALID_PLATFORMS)

        submitted = st.form_submit_button("Submit", use_container_width=True, type="primary")

    if submitted:
        missing = []
        if not auth_token.strip():
            missing.append("Authorization Token")
        if not sourced_id.strip():
            missing.append("Sourced ID")
        if not name.strip():
            missing.append("School Name")
        if not org_ref_id.strip():
            missing.append("Org Ref ID")
        if not platforms:
            missing.append("Platforms")

        if missing:
            log.warning("Single entry validation failed: missing %s", missing)
            st.error(f"Please fill in: **{', '.join(missing)}**")
        else:
            payload = {
                "sourcedId": sourced_id.strip(),
                "name": name.strip(),
                "orgRefId": org_ref_id.strip(),
                "nweaSchoolBid": nwea_school_bid.strip() or "SKIP",
                "platforms": platforms,
            }

            with st.spinner("Sending…"):
                try:
                    resp, cid = send_mapping(auth_token, payload)
                    if 200 <= resp.status_code < 300:
                        log.info("Single entry success: name=%s sourcedId=%s status=%s", payload["name"], payload["sourcedId"], resp.status_code)
                        st.success(f"Success — HTTP {resp.status_code}")
                    else:
                        log.warning("Single entry failed: name=%s status=%s response=%s", payload["name"], resp.status_code, resp.text[:300])
                        st.error(f"Failed — HTTP {resp.status_code}")
                    try:
                        st.json(resp.json())
                    except ValueError:
                        st.code(resp.text)

                    st.session_state.history.insert(0, {
                        "name": name.strip(),
                        "sourcedId": sourced_id.strip(),
                        "status": resp.status_code,
                    })
                except requests.RequestException as e:
                    log.exception("Single entry request failed: %s", e)
                    st.error(f"Request failed: {e}")


# ── Tab 2: CSV bulk upload ──────────────────────────────────────────────────

with tab_csv:
    st.caption(
        "Upload a CSV with columns: **sourcedId**, **name**, **orgRefId** (required), "
        "and optionally **nweaSchoolBid**, **platforms** (comma-separated)."
    )

    sample_csv = "sourcedId,name,orgRefId,nweaSchoolBid,platforms\n69846862a773fdd0a9d5fcb5,Facepink,33b4aa75-9dba-386a-978a-3326e37b369e,SKIP,ED"
    st.download_button(
        "Download sample CSV",
        data=sample_csv,
        file_name="school_mappings_sample.csv",
        mime="text/csv",
    )

    uploaded = st.file_uploader("Choose a CSV file", type=["csv"], key="csv_upload")

    if uploaded is not None:
        log.info("CSV uploaded: name=%s size=%s bytes", uploaded.name, uploaded.size)
        try:
            df = pd.read_csv(uploaded, dtype=str).fillna("")
        except Exception as e:
            log.exception("CSV read failed: %s", e)
            st.error(f"Could not read CSV: {e}")
            st.stop()

        log.info("CSV parsed: rows=%d columns=%s", len(df), list(df.columns))

        missing_cols = REQUIRED_CSV_COLUMNS - set(df.columns)
        if missing_cols:
            log.warning("CSV missing required columns: %s", missing_cols)
            st.error(f"CSV is missing required columns: **{', '.join(sorted(missing_cols))}**")
            st.stop()

        if "nweaSchoolBid" not in df.columns:
            df["nweaSchoolBid"] = "SKIP"
        if "platforms" not in df.columns:
            df["platforms"] = ",".join(VALID_PLATFORMS)

        df["nweaSchoolBid"] = df["nweaSchoolBid"].apply(lambda v: v.strip() if v.strip() else "SKIP")

        preview = df.copy()
        preview.index = range(1, len(preview) + 1)
        preview.index.name = "#"

        st.subheader(f"Preview — {len(df)} mapping(s)")
        st.dataframe(preview, use_container_width=True, height=min(400, 35 * len(df) + 50))

        errors = []
        for idx, row in df.iterrows():
            row_num = idx + 1
            for col in REQUIRED_CSV_COLUMNS:
                if not str(row[col]).strip():
                    errors.append(f"Row {row_num}: **{col}** is empty")
        if errors:
            log.warning("CSV validation errors: %s", errors)
            st.warning("Issues found in CSV:")
            for err in errors:
                st.markdown(f"- {err}")

        if st.button("Send All Mappings", use_container_width=True, type="primary"):
            if not auth_token.strip():
                st.error("Please provide the **Authorization Token** above.")
            elif errors:
                st.error("Fix the CSV issues above before submitting.")
            else:
                log.info("Bulk send started: total_rows=%d file=%s", len(df), uploaded.name)
                progress = st.progress(0, text="Starting…")
                results = []

                for i, (_, row) in enumerate(df.iterrows()):
                    payload = {
                        "sourcedId": str(row["sourcedId"]).strip(),
                        "name": str(row["name"]).strip(),
                        "orgRefId": str(row["orgRefId"]).strip(),
                        "nweaSchoolBid": str(row["nweaSchoolBid"]).strip() or "SKIP",
                        "platforms": parse_platforms(row.get("platforms", "")),
                    }

                    try:
                        resp, cid = send_mapping(auth_token, payload)
                        status = resp.status_code
                        try:
                            body = resp.json()
                        except ValueError:
                            body = resp.text
                        if status and not (200 <= status < 300):
                            log.warning("Bulk row %d failed: name=%s status=%s response=%s", i + 1, payload["name"], status, str(body)[:300])
                    except requests.RequestException as e:
                        status = 0
                        body = str(e)
                        log.exception("Bulk row %d request failed: name=%s error=%s", i + 1, payload["name"], e)

                    results.append({
                        "#": i + 1,
                        "name": payload["name"],
                        "sourcedId": payload["sourcedId"],
                        "status": status,
                        "response": body if not isinstance(body, str) else body,
                    })

                    st.session_state.history.insert(0, {
                        "name": payload["name"],
                        "sourcedId": payload["sourcedId"],
                        "status": status,
                    })

                    pct = (i + 1) / len(df)
                    progress.progress(pct, text=f"Processing {i + 1}/{len(df)} — {payload['name']}")
                    if i < len(df) - 1:
                        time.sleep(0.3)

                progress.empty()

                success_count = sum(1 for r in results if 200 <= r["status"] < 300)
                fail_count = len(results) - success_count
                log.info("Bulk send completed: total=%d success=%d failed=%d", len(results), success_count, fail_count)

                if fail_count == 0:
                    st.success(f"All {success_count} mapping(s) created successfully!")
                elif success_count == 0:
                    st.error(f"All {fail_count} mapping(s) failed.")
                else:
                    st.warning(f"{success_count} succeeded, {fail_count} failed.")

                result_df = pd.DataFrame(results)
                result_df.index = result_df["#"]
                result_df = result_df.drop(columns=["#"])
                st.dataframe(result_df, use_container_width=True)

                for r in results:
                    if r["status"] and not (200 <= r["status"] < 300):
                        with st.expander(f"Error details — {r['name']}"):
                            if isinstance(r["response"], dict):
                                st.json(r["response"])
                            else:
                                st.code(str(r["response"]))


# ── History ─────────────────────────────────────────────────────────────────

if st.session_state.history:
    st.divider()
    st.subheader("History (this session)")
    for i, entry in enumerate(st.session_state.history[:20], 1):
        icon = "✅" if 200 <= entry["status"] < 300 else "❌"
        st.markdown(f"{i}. {icon} **{entry['name']}** (`{entry['sourcedId']}`) — HTTP {entry['status']}")
 
