import logging

def safe_process_data(data):
    try:
        # 初期状態：最低限の設定
        name: demo_project
        debug: true
    except Exception as e:
        logging.error(f"Error processing data: {e}")
        return []
