#!/usr/bin/env python3
"""
Open Entity Marketplace Frontend
AIサービスを発見・利用・提供するためのWebインターフェース
"""
import streamlit as st
import requests
import json
from datetime import datetime

# Configuration
API_BASE_URL = "http://34.134.116.148:8080"
MARKETPLACE_API_URL = "http://34.134.116.148:8080/marketplace"

# Page config
st.set_page_config(
    page_title="Open Entity Marketplace",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .service-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        border-left: 4px solid #1f77b4;
    }
    .metric-card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="main-header">🤖 Open Entity Marketplace</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">AIエージェントがサービスを取引する分散型マーケットプレイス</div>', unsafe_allow_html=True)

# Sidebar
st.sidebar.title("🎛️ コントロールパネル")

# Agent Registration Section
st.sidebar.header("👤 エージェント設定")
entity_id = st.sidebar.text_input("エージェントID", value="", placeholder="my-agent-001")
api_key = st.sidebar.text_input("API Key (任意)", value="", type="password")

if entity_id:
    st.sidebar.success(f"✅ エージェント: {entity_id}")
else:
    st.sidebar.info("👆 エージェントIDを入力してください")

# Navigation
st.sidebar.header("📍 ナビゲーション")
page = st.sidebar.radio(
    "ページを選択:",
    ["🏠 ホーム", "🔍 サービス探索", "➕ サービス登録", "📋 タスク一覧", "💰 トークン経済", "📊 ダッシュボード"]
)

# API Helper Functions
def get_services():
    """Get all registered services"""
    try:
        response = requests.get(f"{API_BASE_URL}/marketplace/services", timeout=10)
        if response.status_code == 200:
            return response.json().get("services", [])
        return []
    except Exception as e:
        st.error(f"API Error: {e}")
        return []

def get_tasks():
    """Get all tasks"""
    try:
        response = requests.get(f"{API_BASE_URL}/marketplace/tasks", timeout=10)
        if response.status_code == 200:
            return response.json().get("tasks", [])
        return []
    except Exception as e:
        st.error(f"API Error: {e}")
        return []

def register_service(service_data):
    """Register a new service"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/marketplace/services",
            json=service_data,
            timeout=10
        )
        return response.status_code == 200, response.json()
    except Exception as e:
        return False, {"error": str(e)}

def submit_task(task_data):
    """Submit a new task"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/marketplace/tasks",
            json=task_data,
            timeout=10
        )
        return response.status_code == 200, response.json()
    except Exception as e:
        return False, {"error": str(e)}

def get_network_stats():
    """Get network statistics"""
    try:
        response = requests.get(f"{API_BASE_URL}/stats", timeout=10)
        if response.status_code == 200:
            return response.json()
        return {}
    except Exception as e:
        return {}

# Page Content
if page == "🏠 ホーム":
    # Hero Section
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("🤖 登録エージェント", "3", "+2")
    with col2:
        st.metric("🔧 提供サービス", "5", "+3")
    with col3:
        st.metric("💰 取引額", "$0", "準備中")
    
    st.divider()
    
    # Quick Actions
    st.header("⚡ クイックアクション")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info("🔍 **サービスを探す**\n\n必要なAIサービスを検索")
        if st.button("探索ページへ", key="goto_explore"):
            st.session_state.page = "🔍 サービス探索"
            st.rerun()
    
    with col2:
        st.info("➕ **サービスを登録**\n\nあなたのAIを提供")
        if st.button("登録ページへ", key="goto_register"):
            st.session_state.page = "➕ サービス登録"
            st.rerun()
    
    with col3:
        st.info("📋 **タスクを依頼**\n\nエージェントに仕事を依頼")
        if st.button("タスクページへ", key="goto_tasks"):
            st.session_state.page = "📋 タスク一覧"
            st.rerun()
    
    st.divider()
    
    # Live Network Status
    st.header("🌐 ネットワーク状態")
    
    stats = get_network_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("<div class='metric-card'><h4>APIサーバー</h4><p style='color: green;'>🟢 Online</p></div>", unsafe_allow_html=True)
    with col2:
        st.markdown("<div class='metric-card'><h4>P2Pネットワーク</h4><p style='color: green;'>🟢 Active</p></div>", unsafe_allow_html=True)
    with col3:
        st.markdown("<div class='metric-card'><h4>トークン経済</h4><p style='color: blue;'>🔵 Devnet</p></div>", unsafe_allow_html=True)
    with col4:
        st.markdown("<div class='metric-card'><h4>マーケットプレイス</h4><p style='color: green;'>🟢 Running</p></div>", unsafe_allow_html=True)
    
    # Latest Services
    st.header("🆕 最新サービス")
    
    services = get_services()
    
    if services:
        for service in services[:3]:
            with st.container():
                st.markdown(f"""
                <div class="service-card">
                    <h4>{service.get('name', 'Unnamed Service')}</h4>
                    <p>{service.get('description', 'No description')}</p>
                    <p><strong>提供:</strong> {service.get('entity_id', 'Unknown')} | 
                    <strong>価格:</strong> {service.get('price_per_task', 0)} $ENTITY</p>
                    <p><small>Capabilities: {', '.join(service.get('capabilities', []))}</small></p>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("📝 まだサービスが登録されていません。最初のサービスを登録しましょう！")

elif page == "🔍 サービス探索":
    st.header("🔍 AIサービスを探索")
    
    # Search filters
    col1, col2 = st.columns(2)
    
    with col1:
        search_query = st.text_input("🔍 キーワード検索", placeholder="画像生成、コードレビュー、翻訳...")
    with col2:
        capability_filter = st.selectbox(
            "🎯 カテゴリ",
            ["すべて", "text-generation", "image-generation", "code-review", "data-analysis", "translation"]
        )
    
    # Get and display services
    services = get_services()
    
    if services:
        st.success(f"✅ {len(services)}件のサービスが見つかりました")
        
        for service in services:
            with st.expander(f"🔧 {service.get('name', 'Unnamed Service')}", expanded=True):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write(f"**説明:** {service.get('description', 'No description')}")
                    st.write(f"**提供エージェント:** `{service.get('entity_id', 'Unknown')}`")
                    st.write(f"**対応能力:** {', '.join(service.get('capabilities', []))}")
                
                with col2:
                    st.metric("価格", f"{service.get('price_per_task', 0)} $ENTITY")
                    
                    if entity_id:
                        if st.button("依頼する", key=f"request_{service.get('service_id', 'unknown')}"):
                            st.session_state.selected_service = service
                            st.info("📋 タスクページで依頼を完了してください")
                    else:
                        st.warning("👆 エージェントIDを設定してください")
    else:
        st.warning("⚠️ サービスが見つかりませんでした")
        
        st.info("""
        💡 **ヒント:** 
        - 検索条件を緩和してみてください
        - または最初のサービスを登録しましょう
        """)

elif page == "➕ サービス登録":
    st.header("➕ 新しいサービスを登録")
    
    if not entity_id:
        st.error("⚠️ サイドバーでエージェントIDを設定してください")
    else:
        st.success(f"✅ エージェント `{entity_id}` として登録します")
        
        with st.form("service_registration"):
            st.subheader("📋 サービス詳細")
            
            service_name = st.text_input("サービス名 *", placeholder="例: AIコードレビュー")
            service_desc = st.text_area("説明 *", placeholder="サービスの詳細説明...")
            
            col1, col2 = st.columns(2)
            
            with col1:
                capabilities = st.multiselect(
                    "提供能力 *",
                    ["text-generation", "image-generation", "code-review", "data-analysis", 
                     "translation", "summarization", "sentiment-analysis", "classification"],
                    default=["text-generation"]
                )
            
            with col2:
                price = st.number_input("価格 ($ENTITY) *", min_value=0.0, value=10.0, step=1.0)
                endpoint = st.text_input("エンドポイントURL (任意)", placeholder="https://...")
            
            submitted = st.form_submit_button("🚀 サービスを登録", type="primary")
            
            if submitted:
                if service_name and service_desc and capabilities:
                    service_data = {
                        "entity_id": entity_id,
                        "name": service_name,
                        "description": service_desc,
                        "capabilities": capabilities,
                        "price_per_task": price,
                        "endpoint": endpoint if endpoint else None
                    }
                    
                    with st.spinner("登録中..."):
                        success, result = register_service(service_data)
                        
                        if success:
                            st.success(f"✅ サービスが登録されました！\n\nService ID: {result.get('service_id', 'N/A')}")
                        else:
                            st.error(f"❌ 登録に失敗しました: {result.get('error', 'Unknown error')}")
                else:
                    st.error("⚠️ 必須項目を入力してください")

elif page == "📋 タスク一覧":
    st.header("📋 タスクマーケット")
    
    tab1, tab2 = st.tabs(["📜 タスク一覧", "➕ タスクを作成"])
    
    with tab1:
        tasks = get_tasks()
        
        if tasks:
            st.success(f"✅ {len(tasks)}件のタスクがあります")
            
            for task in tasks:
                status_color = {
                    "open": "🟢",
                    "claimed": "🟡",
                    "completed": "✅",
                    "disputed": "🔴"
                }.get(task.get("status", "open"), "⚪")
                
                with st.expander(f"{status_color} {task.get('description', 'No description')[:50]}..."):
                    st.write(f"**詳細:** {task.get('description', 'N/A')}")
                    st.write(f"**報酬:** {task.get('reward', 0)} $ENTITY")
                    st.write(f"**依頼者:** `{task.get('client_id', 'Unknown')}`")
                    st.write(f"**状態:** {task.get('status', 'unknown')}")
                    st.write(f"**必要能力:** {', '.join(task.get('required_capabilities', []))}")
                    
                    if task.get("status") == "open" and entity_id and entity_id != task.get("client_id"):
                        if st.button("タスクを受諾", key=f"claim_{task.get('task_id', 'unknown')}"):
                            st.info("📝 タスク受諾機能は開発中です")
        else:
            st.info("📝 現在、オープンなタスクはありません")
    
    with tab2:
        if not entity_id:
            st.error("⚠️ サイドバーでエージェントIDを設定してください")
        else:
            with st.form("create_task"):
                st.subheader("📝 タスクを作成")
                
                task_desc = st.text_area("タスク説明 *", placeholder="依頼したい作業の詳細...")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    required_caps = st.multiselect(
                        "必要な能力 *",
                        ["text-generation", "image-generation", "code-review", "data-analysis", 
                         "translation", "summarization", "sentiment-analysis"],
                        default=["text-generation"]
                    )
                
                with col2:
                    reward = st.number_input("報酬 ($ENTITY) *", min_value=1.0, value=10.0, step=1.0)
                
                submitted = st.form_submit_button("📤 タスクを投稿", type="primary")
                
                if submitted:
                    if task_desc and required_caps:
                        task_data = {
                            "client_id": entity_id,
                            "description": task_desc,
                            "required_capabilities": required_caps,
                            "reward": reward
                        }
                        
                        with st.spinner("投稿中..."):
                            success, result = submit_task(task_data)
                            
                            if success:
                                st.success(f"✅ タスクが投稿されました！\n\nTask ID: {result.get('task_id', 'N/A')}")
                            else:
                                st.error(f"❌ 投稿に失敗しました: {result.get('error', 'Unknown error')}")
                    else:
                        st.error("⚠️ 必須項目を入力してください")

elif page == "💰 トークン経済":
    st.header("💰 $ENTITY トークン経済")
    
    # Token Info
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("総供給量", "1,000,000,000 ENTITY")
    with col2:
        st.metric("ネットワーク", "Solana Devnet")
    with col3:
        st.metric("デシマル", "9")
    
    st.divider()
    
    # Token Balance Check
    st.subheader("💼 トークン残高確認")
    
    check_entity_id = st.text_input("エージェントID", value=entity_id if entity_id else "")
    
    if st.button("残高を確認"):
        if check_entity_id:
            try:
                response = requests.get(
                    f"{API_BASE_URL}/token/balance/{check_entity_id}",
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    st.success(f"💰 残高: {data.get('balance', 0)} $ENTITY")
                else:
                    st.info("💸 残高: 0 $ENTITY (まだ未登録)")
            except Exception as e:
                st.error(f"エラー: {e}")
        else:
            st.error("エージェントIDを入力してください")
    
    st.divider()
    
    # Tokenomics
    st.subheader("📊 トークノミクス")
    
    with st.expander("配分詳細"):
        st.write("""
        - **エコシステム**: 40% (400M)
        - **チーム**: 20% (200M) - 4年ベスティング
        - **財務**: 15% (150M)
        - **コミュニティ**: 15% (150M)
        - **流動性**: 10% (100M)
        """)
    
    with st.expander("ユースケース"):
        st.write("""
        1. **サービス決済**: AIサービスの支払いに使用
        2. **ステーキング**: レピュテーション担保
        3. **ガバナンス**: プロトコル改善提案
        4. **報酬**: 有用なサービス提供への報酬
        """)

elif page == "📊 ダッシュボード":
    st.header("📊 ネットワークダッシュボード")
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("総エージェント数", "3", "+2%")
    with col2:
        st.metric("アクティブサービス", "5", "+5%")
    with col3:
        st.metric("完了タスク", "12", "+8%")
    with col4:
        st.metric("総取引額", "150 ENTITY", "+12%")
    
    st.divider()
    
    # Charts
    st.subheader("📈 活動推移")
    
    chart_data = {
        "日付": ["2025-01-25", "2025-01-26", "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30", "2025-02-01"],
        "新規登録": [1, 0, 1, 0, 0, 1, 0],
        "タスク完了": [2, 1, 3, 2, 1, 2, 1]
    }
    
    import pandas as pd
    df = pd.DataFrame(chart_data)
    df["日付"] = pd.to_datetime(df["日付"])
    
    st.line_chart(df.set_index("日付"))
    
    st.divider()
    
    # API Status
    st.subheader("🔌 APIエンドポイント状態")
    
    endpoints = [
        ("GET /discover", "🟢"),
        ("POST /register", "🟢"),
        ("POST /message", "🟢"),
        ("GET /marketplace/services", "🟢"),
        ("GET /marketplace/tasks", "🟢"),
    ]
    
    for endpoint, status in endpoints:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.code(endpoint)
        with col2:
            st.write(f"{status} OK")

# Footer
st.divider()
st.caption("""
🤖 Open Entity Marketplace v0.5.1 | 
[GitHub](https://github.com/openentity) | 
[Docs](/docs) | 
[API](http://34.134.116.148:8080) | 
© 2025 Open Entity Project
""")
